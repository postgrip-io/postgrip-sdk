package worker

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/activity"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
)

const taskCancelledBody = `{"code":"TASK_CANCELLED","message":"task was cancelled: task is already terminal","requestId":"req-1"}`

func TestIsTerminalTaskMutation(t *testing.T) {
	conflict := func(status int, code, message string) error {
		body := `{"code":"` + code + `","message":"` + message + `","requestId":"req-1"}`
		return &failure.SDKError{Message: "http request", StatusCode: status, Code: code, ResponseBody: []byte(body)}
	}
	for _, tc := range []struct {
		err  error
		want bool
	}{
		{conflict(http.StatusConflict, "TASK_CANCELLED", "task was cancelled: task is already terminal"), true},
		{conflict(http.StatusConflict, "TASK_CANCELLED", "cancelled"), true},
		{conflict(http.StatusConflict, "CONFLICT", "task is already terminal"), true},
		{conflict(http.StatusConflict, "CONFLICT", "task is not leased by agent"), true},
		{conflict(http.StatusConflict, "CONFLICT", "workflow exists"), false},
		{conflict(http.StatusInternalServerError, "TASK_CANCELLED", "task is already terminal"), false},
		{errors.New("task is already terminal"), false},
		{nil, false},
	} {
		if got := isTerminalTaskMutation(tc.err); got != tc.want {
			t.Errorf("isTerminalTaskMutation(%v) = %v, want %v", tc.err, got, tc.want)
		}
	}
}

// A heartbeat answered 409 TASK_CANCELLED (the task was cancelled with
// cancelTask) stops the task: its context is cancelled with errTaskStopped,
// heartbeats stop, and neither complete nor fail is sent.
func TestHeartbeatTaskCancelledStopsTheTaskWithoutReporting(t *testing.T) {
	t.Parallel()
	var (
		mu       sync.Mutex
		paths    []string
		polled   atomic.Bool
		finished = make(chan error, 1)
	)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		paths = append(paths, r.URL.Path)
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/api/v1/agent/poll":
			if polled.Swap(true) {
				_, _ = w.Write([]byte(`{}`))
				return
			}
			_, _ = w.Write([]byte(`{"task":{"id":"task-1","type":"activity:Wait","state":"leased","lease_timeout_seconds":1,"payload":{"activityType":"Wait"}}}`))
		case strings.HasSuffix(r.URL.Path, "/heartbeat"):
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(taskCancelledBody))
		case strings.HasSuffix(r.URL.Path, "/events"):
			_, _ = w.Write([]byte(`{}`))
		default:
			t.Errorf("unexpected report %s %s", r.Method, r.URL.Path)
			_, _ = w.Write([]byte(`{}`))
		}
	}))
	defer server.Close()

	conn, err := client.NewConnection(client.ConnectionOptions{Address: server.URL, InsecureDevelopment: true})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "agent-token", time.Now().Add(time.Hour))
	w, err := New(Options{
		Connection:   conn,
		AgentID:      "agent-1",
		PollInterval: 10 * time.Millisecond,
		Logger:       slog.New(slog.NewTextHandler(io.Discard, nil)),
		Activities: activity.Registry{
			"Wait": func(ctx context.Context, _ []any) (any, error) {
				<-ctx.Done()
				finished <- context.Cause(ctx)
				return nil, ctx.Err()
			},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	go func() { _ = w.Run(ctx) }()

	select {
	case cause := <-finished:
		if !errors.Is(cause, errTaskStopped) {
			t.Fatalf("task context cause = %v, want errTaskStopped", cause)
		}
	case <-ctx.Done():
		t.Fatal("the cancelled task kept running")
	}
	// Leave time for a report or another heartbeat that must not come.
	time.Sleep(700 * time.Millisecond)
	if err := w.Shutdown(context.Background(), time.Second); err != nil {
		t.Fatal(err)
	}
	mu.Lock()
	defer mu.Unlock()
	heartbeats := 0
	for _, path := range paths {
		if strings.HasSuffix(path, "/heartbeat") {
			heartbeats++
		}
	}
	if heartbeats != 1 {
		t.Fatalf("heartbeats = %d (%v), want renewal to stop after the cancel", heartbeats, paths)
	}
}

// activity.Heartbeat reports a cancelled task as cancellation, as the
// TypeScript and Python heartbeat helpers do.
func TestActivityHeartbeatOfACancelledTaskIsCancellation(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(taskCancelledBody))
	}))
	defer server.Close()
	conn, err := client.NewConnection(client.ConnectionOptions{Address: server.URL, InsecureDevelopment: true})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "agent-token", time.Now().Add(time.Hour))
	var heartbeatErr, milestoneErr error
	w, err := New(Options{Connection: conn, AgentID: "agent-1", Activities: activity.Registry{
		"Beat": func(ctx context.Context, _ []any) (any, error) {
			heartbeatErr = activity.Heartbeat(ctx, nil)
			milestoneErr = activity.Milestone(ctx, "step", activity.MilestoneOptions{})
			return nil, nil
		},
	}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.runActivity(context.Background(), &client.Task{ID: "task-1", Type: "activity:Beat"}); err != nil {
		t.Fatal(err)
	}
	if !failure.IsCancelled(heartbeatErr) {
		t.Fatalf("Heartbeat error = %v, want cancellation", heartbeatErr)
	}
	if failure.IsCancelled(milestoneErr) || milestoneErr == nil {
		t.Fatalf("Milestone error = %v, want the plain 409", milestoneErr)
	}
}
