package client

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
)

type recordedAgentBody struct {
	path   string
	header http.Header
	body   string
}

func agentBodyRecordingServer(t *testing.T, respond func(attempt int, w http.ResponseWriter, r *http.Request)) (*Connection, func() []recordedAgentBody) {
	t.Helper()
	var mu sync.Mutex
	var bodies []recordedAgentBody
	server, _ := agentRecordingServer(t, func(attempt int, w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		mu.Lock()
		bodies = append(bodies, recordedAgentBody{path: r.URL.Path, header: r.Header.Clone(), body: string(raw)})
		mu.Unlock()
		respond(attempt, w, r)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt-management", EnableRetries: true})
	if err != nil {
		t.Fatal(err)
	}
	return conn, func() []recordedAgentBody {
		mu.Lock()
		defer mu.Unlock()
		return append([]recordedAgentBody(nil), bodies...)
	}
}

func TestTaskCancelPostsTheReasonAndReturnsTheTask(t *testing.T) {
	conn, requests := agentBodyRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, `{"id":"task-1","state":"failed","error":"task cancelled: superseded","result":{"failure":{"type":"TaskCancelled","message":"superseded","non_retryable":true}}}`)
	})
	tasks := New(conn).Task

	task, err := tasks.Cancel(context.Background(), "task-1", "superseded")
	if err != nil {
		t.Fatal(err)
	}
	if task.ID != "task-1" || task.State != TaskStateFailed || task.Result == nil || task.Result.Failure == nil || task.Result.Failure.Type != "TaskCancelled" {
		t.Fatalf("task = %+v, want the cancelled task", task)
	}
	if _, err := tasks.Cancel(context.Background(), "task-1", ""); err != nil {
		t.Fatal(err)
	}
	got := requests()
	if got[0].path != "/api/v1/tasks/task-1/cancel" || got[0].body != `{"reason":"superseded"}` {
		t.Fatalf("request = %s %s, want the reason posted to the cancel path", got[0].path, got[0].body)
	}
	if got[1].body != `{}` {
		t.Fatalf("cancel without a reason body = %s, want {}", got[1].body)
	}
	if got[0].header.Get("Authorization") != "Bearer pgt-management" || got[0].header.Get("Idempotency-Key") != "" {
		t.Fatalf("headers = %v, want the management bearer and no key", got[0].header)
	}
}

func TestTaskCancelOfAFinishedTaskIsATaskTerminalConflict(t *testing.T) {
	conn, requests := agentBodyRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusConflict, `{"code":"TASK_TERMINAL","message":"task is already terminal","requestId":"req-1","details":{"state":"succeeded"}}`)
	})
	_, err := conn.CancelTask(context.Background(), "task-1", "")
	var sdkErr *failure.SDKError
	if !errors.As(err, &sdkErr) || sdkErr.StatusCode != http.StatusConflict || sdkErr.Code != "TASK_TERMINAL" || sdkErr.Details["state"] != "succeeded" {
		t.Fatalf("error = %#v, want 409 TASK_TERMINAL with details.state", err)
	}
	if len(requests()) != 1 {
		t.Fatalf("attempts = %d, want the conflict answered once", len(requests()))
	}
}

func TestTaskSendsAndSignalsCarryAnOptionalIdempotencyKey(t *testing.T) {
	conn, requests := agentBodyRecordingServer(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/signal-with-start") {
			writeJSON(w, http.StatusOK, `{"workflow":{"id":"order-42"},"task":{"id":"task-9"},"signal":{"id":"evt-1"}}`)
			return
		}
		writeJSON(w, http.StatusOK, `{"id":"task-1"}`)
	})
	conn.SeedAgentSession("agent-1", "tok", time.Now().Add(time.Hour))
	c := New(conn)
	ctx := context.Background()

	if _, err := c.Task.Enqueue(ctx, EnqueueInput{Type: TaskTypeNoop, IdempotencyKey: "ci-run-4512"}); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Task.Enqueue(ctx, EnqueueInput{Type: TaskTypeNoop}); err != nil {
		t.Fatal(err)
	}
	if err := c.Workflow.GetHandle("order-42").Signal(WithIdempotencyKey(ctx, "approve-1"), "approve"); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Workflow.SignalWithStart(ctx, "OrderWorkflow", "approve", SignalWithStartOptions{
		WorkflowStartOptions: WorkflowStartOptions{WorkflowID: "order-42"},
		IdempotencyKey:       "approve-2",
	}); err != nil {
		t.Fatal(err)
	}
	// A key on the context reaches only the operations that declare it.
	if _, err := c.Task.Get(WithIdempotencyKey(ctx, "unused"), "task-1"); err != nil {
		t.Fatal(err)
	}
	var out json.RawMessage
	if err := conn.OpenAPI().Do(ctx, "enqueueTask", nil, nil, http.Header{"Idempotency-Key": {"raw-1"}}, EnqueueTaskRequest{Type: TaskTypeNoop}, &out); err != nil {
		t.Fatal(err)
	}

	want := []string{"ci-run-4512", "", "approve-1", "approve-2", "", "raw-1"}
	got := requests()
	if len(got) != len(want) {
		t.Fatalf("requests = %d, want %d", len(got), len(want))
	}
	for i, key := range want {
		if value := got[i].header.Get("Idempotency-Key"); value != key {
			t.Fatalf("request %d %s Idempotency-Key = %q, want %q", i, got[i].path, value, key)
		}
	}
}

func TestOptionalIdempotencyKeyIsValidatedAndMakesTheSendRetryable(t *testing.T) {
	conn, requests := agentBodyRecordingServer(t, func(attempt int, w http.ResponseWriter, _ *http.Request) {
		if attempt == 1 {
			w.Header().Set("Retry-After", "0")
			writeJSON(w, http.StatusServiceUnavailable, `{"code":"BUSY","message":"busy","requestId":"req-1"}`)
			return
		}
		writeJSON(w, http.StatusOK, `{"id":"task-1"}`)
	})
	tasks := New(conn).Task

	if _, err := tasks.Enqueue(context.Background(), EnqueueInput{Type: TaskTypeNoop, IdempotencyKey: "not valid"}); err == nil || !strings.Contains(err.Error(), "idempotency key") {
		t.Fatalf("invalid key error = %v", err)
	}
	if len(requests()) != 0 {
		t.Fatal("an invalid key reached the server")
	}
	if _, err := tasks.Enqueue(context.Background(), EnqueueInput{Type: TaskTypeNoop, IdempotencyKey: "ci-run-4512"}); err != nil {
		t.Fatal(err)
	}
	if got := requests(); len(got) != 2 || got[1].header.Get("Idempotency-Key") != "ci-run-4512" || got[1].body != got[0].body {
		t.Fatalf("requests = %+v, want the keyed send retried once with the same key and body", got)
	}
	if err := conn.OpenAPI().Do(context.Background(), "getTask", map[string]string{"taskId": "task-1"}, nil, http.Header{"Idempotency-Key": {"k"}}, nil, nil); err == nil {
		t.Fatal("Do sent a header the operation does not declare")
	}
}
