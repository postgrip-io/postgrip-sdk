package worker

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow"
)

// ownershipServer serves a workflow's history plus command tasks, each of
// which names its scheduling task in its payload, and records requests.
type ownershipServer struct {
	history string
	// tasks maps a command task ID to its owner and state; an empty owner
	// makes the task read fail, and "none" serves a payload naming no owner.
	tasks map[string][2]string
	// failAfterFirstRead makes every read of the task after the first fail.
	failAfterFirstRead map[string]bool
	mu                 sync.Mutex
	paths              []string
	reads              map[string]int
}

func (s *ownershipServer) start(t *testing.T) *client.Connection {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		s.mu.Lock()
		s.paths = append(s.paths, r.Method+" "+r.URL.Path)
		s.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.HasSuffix(r.URL.Path, "/history"):
			_, _ = w.Write([]byte(`{"items":` + s.history + `}`))
		case r.Method == http.MethodGet && r.URL.Path == "/api/v1/workflows/run-1":
			_, _ = w.Write([]byte(`{"id":"workflow-1","run_id":"run-1","namespace":"default","type":"Owned","queue":"default","task_id":"wf-task","state":"running","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		case r.Method == http.MethodGet && r.URL.Path == "/api/v1/tasks/wf-task":
			_, _ = w.Write([]byte(`{"id":"wf-task","namespace":"default","queue":"default","type":"workflow:Owned","state":"blocked","attempt":1,"lease_timeout_seconds":30,"payload":{"workflowType":"Owned","workflowId":"workflow-1","runId":"run-1","args":[]},"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/api/v1/tasks/"):
			id := strings.TrimPrefix(r.URL.Path, "/api/v1/tasks/")
			s.mu.Lock()
			if s.reads == nil {
				s.reads = map[string]int{}
			}
			s.reads[id]++
			read := s.reads[id]
			s.mu.Unlock()
			task, ok := s.tasks[id]
			if !ok || task[0] == "" || (s.failAfterFirstRead[id] && read > 1) {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte(`{"code":"UNAVAILABLE","message":"unavailable"}`))
				return
			}
			payload := fmt.Sprintf(`{"workflowTaskId":%q}`, task[0])
			if task[0] == "none" {
				payload = `{}`
			}
			_, _ = fmt.Fprintf(w, `{"id":%q,"namespace":"default","queue":"default","type":"activity:X","state":%q,"attempt":1,"lease_timeout_seconds":30,"result":{"value":"ok"},"payload":%s,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`, id, task[1], payload)
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/block"):
			_, _ = w.Write([]byte(`{"id":"blocked","namespace":"default","queue":"default","type":"workflow:Owned","state":"blocked","attempt":1,"lease_timeout_seconds":30,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		default:
			http.Error(w, "unexpected request "+r.Method+" "+r.URL.Path, http.StatusBadRequest)
		}
	}))
	t.Cleanup(server.Close)
	conn, err := client.NewConnection(client.ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "tok"})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "tok", time.Now().Add(time.Hour))
	return conn
}

func (s *ownershipServer) requested(path string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, p := range s.paths {
		if p == path {
			return true
		}
	}
	return false
}

func ownedWorker(t *testing.T, conn *client.Connection, fn workflow.Func) *Worker {
	t.Helper()
	w, err := New(Options{Connection: conn, AgentID: "agent-1", Workflows: workflow.Registry{"Owned": fn}})
	if err != nil {
		t.Fatal(err)
	}
	return w
}

func runOwnedWorkflow(w *Worker) (*client.TaskResult, error) {
	payload, _ := json.Marshal(map[string]any{"workflowType": "Owned", "workflowId": "workflow-1", "runId": "run-1", "args": []any{}})
	return w.runWorkflow(context.Background(), &client.Task{
		ID: "wf-task", Namespace: "default", Queue: "default", Type: client.TaskTypePrefixWorkflow + "Owned", Payload: payload,
	})
}

func wantDeterminism(t *testing.T, err error, contains string) {
	t.Helper()
	var app *failure.Application
	if !errors.As(err, &app) || app.Type != "WorkflowDeterminismViolation" || !strings.Contains(app.Message, contains) {
		t.Fatalf("err = %v, want WorkflowDeterminismViolation containing %q", err, contains)
	}
}

// A replayed update handler consumes the commands it recorded, even when the
// body recorded a command between them; one shared cursor would fail here.
func TestReplayedUpdateHandlerConsumesItsOwnCommands(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-body","type":"ActivityTaskScheduled","attributes":{"activity_type":"Greet"},"created_at":"2026-01-01T00:00:01Z"},
			{"id":"e3","workflow_id":"workflow-1","task_id":"act-update","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:02Z"},
			{"id":"e4","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateCompleted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:03Z"}
		]`,
		tasks: map[string][2]string{"act-body": {"wf-task", "succeeded"}, "act-update": {"update-1", "succeeded"}},
	}
	conn := s.start(t)
	approved := false
	w := ownedWorker(t, conn, func(ctx workflow.Context, _ []any) (any, error) {
		if err := ctx.SetUpdateHandler("approve", func(_ []any) (any, error) {
			approved = true
			return nil, ctx.ExecuteActivity("Validate", nil, nil, nil)
		}); err != nil {
			return nil, err
		}
		if err := ctx.ExecuteActivity("Greet", nil, nil, nil); err != nil {
			return nil, err
		}
		return "done", nil
	})
	result, err := runOwnedWorkflow(w)
	if err != nil || result == nil || result.Value != "done" || !approved {
		t.Fatalf("runWorkflow = %#v, %v (approved=%v); want done", result, err, approved)
	}
}

// A workflow that completes before replaying a recorded body command fails the
// completion check instead of completing.
func TestRunWorkflowFailsWhenCompletingBeforeRecordedCommands(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{history: `[{"id":"e1","workflow_id":"workflow-1","task_id":"act-1","type":"ActivityTaskScheduled","attributes":{"activity_type":"Greet"},"created_at":"2026-01-01T00:00:00Z"}]`}
	w := ownedWorker(t, s.start(t), func(workflow.Context, []any) (any, error) { return "done", nil })
	_, err := runOwnedWorkflow(w)
	wantDeterminism(t, err, "finished before replaying recorded command")
}

// Continuing as new is a completion, so it runs the same check.
func TestContinueAsNewFailsBeforeRecordedCommands(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{history: `[{"id":"e1","workflow_id":"workflow-1","task_id":"act-1","type":"ActivityTaskScheduled","attributes":{"activity_type":"Greet"},"created_at":"2026-01-01T00:00:00Z"}]`}
	w := ownedWorker(t, s.start(t), func(ctx workflow.Context, _ []any) (any, error) {
		return nil, ctx.ContinueAsNew(workflow.ContinueAsNewOptions{})
	})
	_, err := runOwnedWorkflow(w)
	wantDeterminism(t, err, "finished before replaying recorded command")
}

// An owner that cannot be read is treated like a failed history fetch: the
// workflow task is blocked for redelivery rather than replayed.
func TestRunWorkflowBlocksWhenCommandOwnerReadFails(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-unreadable","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:01Z"}
		]`,
		tasks: map[string][2]string{"act-unreadable": {"", ""}},
	}
	conn := s.start(t)
	ran := false
	w := ownedWorker(t, conn, func(workflow.Context, []any) (any, error) {
		ran = true
		return "done", nil
	})
	if _, err := runOwnedWorkflow(w); !errors.Is(err, errWorkflowAlreadyBlocked) {
		t.Fatalf("err = %v, want errWorkflowAlreadyBlocked", err)
	}
	if ran || !s.requested("POST /api/v1/agent/tasks/wf-task/block") {
		t.Fatalf("ran=%v blocked=%v; want the task blocked without running", ran, s.requested("POST /api/v1/agent/tasks/wf-task/block"))
	}
}

// A live update handler first replays the commands it recorded on an earlier
// delivery of its task, while the body replays its own, then continues.
func TestLiveUpdateHandlerReplaysItsEarlierCommands(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-task-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-update","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:01Z"},
			{"id":"e3","workflow_id":"workflow-1","task_id":"timer-body","type":"TimerStarted","attributes":{"duration_ms":3600000},"created_at":"2026-01-01T00:00:02Z"}
		]`,
		tasks: map[string][2]string{"act-update": {"update-task-1", "succeeded"}, "timer-body": {"wf-task", "queued"}},
	}
	conn := s.start(t)
	w := ownedWorker(t, conn, func(ctx workflow.Context, _ []any) (any, error) {
		if err := ctx.SetUpdateHandler("approve", func(_ []any) (any, error) {
			if err := ctx.ExecuteActivity("Validate", nil, nil, nil); err != nil {
				return nil, err
			}
			return "approved", nil
		}); err != nil {
			return nil, err
		}
		return nil, ctx.Sleep(time.Hour)
	})
	payload, _ := json.Marshal(client.WorkflowUpdatePayload{
		WorkflowID: "workflow-1", WorkflowRunID: "run-1", WorkflowType: "Owned", UpdateName: "approve", Args: json.RawMessage(`[]`),
	})
	result, err := w.runWorkflowUpdate(context.Background(), &client.Task{
		ID: "update-task-1", Type: "update:Owned", Namespace: "default", Queue: "default", Payload: payload,
	})
	if err != nil || result == nil || result.Value != "approved" {
		t.Fatalf("runWorkflowUpdate = %#v, %v; want approved", result, err)
	}
	if s.requested("POST /api/v1/tasks") {
		t.Fatal("the live handler scheduled its recorded activity again")
	}
}

// A query replay that returns normally must have consumed every recorded body
// command, so the query never answers from inconsistent state.
func TestQueryReplayFailsWhenReturningBeforeRecordedCommands(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{history: `[{"id":"e1","workflow_id":"workflow-1","task_id":"act-1","type":"ActivityTaskScheduled","attributes":{"activity_type":"Greet"},"created_at":"2026-01-01T00:00:00Z"}]`}
	w := ownedWorker(t, s.start(t), func(ctx workflow.Context, _ []any) (any, error) {
		return "done", ctx.SetQueryHandler("status", func([]any) (any, error) { return "ready", nil })
	})
	payload, _ := json.Marshal(client.WorkflowQueryPayload{
		WorkflowID: "workflow-1", WorkflowRunID: "run-1", WorkflowType: "Owned", QueryName: "status", Args: json.RawMessage(`[]`),
	})
	_, err := w.runWorkflowQuery(context.Background(), &client.Task{
		ID: "query-task-1", Type: "query:Owned", Namespace: "default", Queue: "default", Payload: payload,
	})
	wantDeterminism(t, err, "finished before replaying recorded command")
}

// A live update handler that returns after replaying only part of the commands
// it recorded on an earlier delivery is a determinism error.
func TestLiveUpdateHandlerLeavingRecordedCommandsFails(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-task-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-validate","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:01Z"},
			{"id":"e3","workflow_id":"workflow-1","task_id":"act-notify","type":"ActivityTaskScheduled","attributes":{"activity_type":"Notify"},"created_at":"2026-01-01T00:00:02Z"},
			{"id":"e4","workflow_id":"workflow-1","task_id":"timer-body","type":"TimerStarted","attributes":{"duration_ms":3600000},"created_at":"2026-01-01T00:00:03Z"}
		]`,
		tasks: map[string][2]string{
			"act-validate": {"update-task-1", "succeeded"}, "act-notify": {"update-task-1", "succeeded"}, "timer-body": {"wf-task", "queued"},
		},
	}
	w := ownedWorker(t, s.start(t), func(ctx workflow.Context, _ []any) (any, error) {
		if err := ctx.SetUpdateHandler("approve", func(_ []any) (any, error) {
			return "approved", ctx.ExecuteActivity("Validate", nil, nil, nil)
		}); err != nil {
			return nil, err
		}
		return nil, ctx.Sleep(time.Hour)
	})
	payload, _ := json.Marshal(client.WorkflowUpdatePayload{
		WorkflowID: "workflow-1", WorkflowRunID: "run-1", WorkflowType: "Owned", UpdateName: "approve", Args: json.RawMessage(`[]`),
	})
	_, err := w.runWorkflowUpdate(context.Background(), &client.Task{
		ID: "update-task-1", Type: "update:Owned", Namespace: "default", Queue: "default", Payload: payload,
	})
	wantDeterminism(t, err, "finished before replaying recorded command")
}

// A transport failure inside a replayed handler propagates unchanged, so the
// task is redelivered rather than failed as nondeterministic.
func TestReplayedHandlerTransportErrorIsNotADeterminismError(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-validate","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:01Z"},
			{"id":"e3","workflow_id":"workflow-1","task_id":"act-notify","type":"ActivityTaskScheduled","attributes":{"activity_type":"Notify"},"created_at":"2026-01-01T00:00:02Z"},
			{"id":"e4","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateCompleted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:03Z"}
		]`,
		tasks: map[string][2]string{"act-validate": {"update-1", "succeeded"}, "act-notify": {"update-1", "succeeded"}},
		// The owner read succeeds; resolving the activity's result then fails.
		failAfterFirstRead: map[string]bool{"act-validate": true},
	}
	w := ownedWorker(t, s.start(t), func(ctx workflow.Context, _ []any) (any, error) {
		if err := ctx.SetUpdateHandler("approve", func(_ []any) (any, error) {
			if err := ctx.ExecuteActivity("Validate", nil, nil, nil); err != nil {
				return nil, err
			}
			return nil, ctx.ExecuteActivity("Notify", nil, nil, nil)
		}); err != nil {
			return nil, err
		}
		return "done", nil
	})
	_, err := runOwnedWorkflow(w)
	var sdkErr *failure.SDKError
	var app *failure.Application
	if !errors.As(err, &sdkErr) || (errors.As(err, &app) && app.Type == "WorkflowDeterminismViolation") {
		t.Fatalf("err = %v, want the transport error, not a determinism violation", err)
	}
}

// A replayed handler's own command never applies a later update boundary, so
// overlapping updates replay in acceptance order.
func TestReplayedHandlerCommandsDoNotApplyLaterUpdates(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":["first"]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"update-2","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":["second"]},"created_at":"2026-01-01T00:00:01Z"},
			{"id":"e3","workflow_id":"workflow-1","task_id":"act-1","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:02Z"},
			{"id":"e4","workflow_id":"workflow-1","task_id":"act-2","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:03Z"},
			{"id":"e5","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateCompleted","attributes":{"update_name":"approve","args":["first"]},"created_at":"2026-01-01T00:00:04Z"},
			{"id":"e6","workflow_id":"workflow-1","task_id":"update-2","type":"WorkflowUpdateCompleted","attributes":{"update_name":"approve","args":["second"]},"created_at":"2026-01-01T00:00:05Z"}
		]`,
		tasks: map[string][2]string{"act-1": {"update-1", "succeeded"}, "act-2": {"update-2", "succeeded"}},
	}
	var order []string
	w := ownedWorker(t, s.start(t), func(ctx workflow.Context, _ []any) (any, error) {
		if err := ctx.SetUpdateHandler("approve", func(args []any) (any, error) {
			if err := ctx.ExecuteActivity("Validate", nil, nil, nil); err != nil {
				return nil, err
			}
			order = append(order, args[0].(string))
			return nil, nil
		}); err != nil {
			return nil, err
		}
		return "done", nil
	})
	if _, err := runOwnedWorkflow(w); err != nil {
		t.Fatalf("runWorkflow: %v", err)
	}
	if len(order) != 2 || order[0] != "first" || order[1] != "second" {
		t.Fatalf("handler order = %v, want [first second]", order)
	}
}

// A command task whose payload names no scheduling task is unreadable, not
// body-owned, so the workflow task is blocked for redelivery.
func TestRunWorkflowBlocksWhenCommandOwnerIsMissing(t *testing.T) {
	t.Parallel()
	s := &ownershipServer{
		history: `[
			{"id":"e1","workflow_id":"workflow-1","task_id":"update-1","type":"WorkflowUpdateAccepted","attributes":{"update_name":"approve","args":[]},"created_at":"2026-01-01T00:00:00Z"},
			{"id":"e2","workflow_id":"workflow-1","task_id":"act-ownerless","type":"ActivityTaskScheduled","attributes":{"activity_type":"Validate"},"created_at":"2026-01-01T00:00:01Z"}
		]`,
		tasks: map[string][2]string{"act-ownerless": {"none", "succeeded"}},
	}
	w := ownedWorker(t, s.start(t), func(workflow.Context, []any) (any, error) { return "done", nil })
	if _, err := runOwnedWorkflow(w); !errors.Is(err, errWorkflowAlreadyBlocked) {
		t.Fatalf("err = %v, want errWorkflowAlreadyBlocked", err)
	}
}
