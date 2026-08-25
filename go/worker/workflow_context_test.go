package worker

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/failure"
	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/replay"
	"github.com/postgrip-io/postgrip-agent-sdks/go/workflow"
)

func TestSignalChannelDrainsThenSuspends(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, []client.WorkflowHistoryEvent{
		{Type: replay.EventWorkflowSignaled, Attributes: map[string]any{"name": "ready", "args": []any{"a"}}},
		{Type: replay.EventWorkflowSignaled, Attributes: map[string]any{"name": "ready", "args": []any{"b"}}},
	})
	ch := wfctx.GetSignalChannel("ready")
	args, err := ch.Receive(wfctx)
	if err != nil || args[0] != "a" {
		t.Fatalf("first receive = %v, err=%v", args, err)
	}
	args, err = ch.Receive(wfctx)
	if err != nil || args[0] != "b" {
		t.Fatalf("second receive = %v, err=%v", args, err)
	}
	if _, err := ch.Receive(wfctx); !workflow.IsSuspended(err) {
		t.Fatalf("expected suspend after draining buffer, got %v", err)
	}
}

func TestSleepReturnsNilWhenTimerFiredInHistory(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, []client.WorkflowHistoryEvent{
		{Type: replay.EventTimerStarted, TaskID: "tmr-1", Attributes: map[string]any{"duration_ms": float64(1500)}},
		{Type: replay.EventTimerFired, TaskID: "tmr-1"},
	})
	if err := wfctx.Sleep(1500 * time.Millisecond); err != nil {
		t.Fatalf("Sleep with fired timer = %v, want nil", err)
	}
}

func TestSleepSuspendsWhenTimerStillPending(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, []client.WorkflowHistoryEvent{
		{Type: replay.EventTimerStarted, TaskID: "tmr-1", Attributes: map[string]any{"duration_ms": float64(1500)}},
	})
	err := wfctx.Sleep(1500 * time.Millisecond)
	if !workflow.IsSuspended(err) {
		t.Fatalf("expected suspend when timer pending, got %v", err)
	}
}

func TestSleepSchedulesAndSuspendsWhenHistoryExhausted(t *testing.T) {
	t.Parallel()
	var seenType string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req client.EnqueueTaskRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		seenType = req.Type
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"tmr-new","namespace":"default","queue":"default","type":"timer","state":"queued","attempt":0,"lease_timeout_seconds":0,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
	}))
	defer server.Close()

	conn, _ := client.NewConnection(client.ConnectionOptions{Address: server.URL})
	conn.SeedAgentSession("agent-1", "tok", time.Now().Add(time.Hour))
	wfctx := &workflowContext{
		Context:    context.Background(),
		logger:     slog.Default(),
		conn:       conn,
		namespace:  "default",
		queue:      "default",
		taskID:     "wf-task",
		workflowID: "wf-1",
		now:        time.Now().UTC(),
		replay:     replay.New(nil),
	}
	err := wfctx.Sleep(2 * time.Second)
	if !workflow.IsSuspended(err) {
		t.Fatalf("expected suspend after scheduling timer, got %v", err)
	}
	if seenType != client.TaskTypeTimer {
		t.Fatalf("scheduled type = %q, want timer", seenType)
	}
}

func TestExecuteActivityReturnsHistoryResult(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"act-1","namespace":"default","queue":"default","type":"activity:Greet","state":"succeeded","attempt":1,"lease_timeout_seconds":0,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:01Z","result":{"value":"hello, world"}}`))
	}))
	defer server.Close()

	conn, _ := client.NewConnection(client.ConnectionOptions{Address: server.URL})
	wfctx := &workflowContext{
		Context: context.Background(),
		logger:  slog.Default(),
		conn:    conn,
		replay: replay.New([]client.WorkflowHistoryEvent{
			{Type: replay.EventActivityTaskScheduled, TaskID: "act-1", Attributes: map[string]any{"activity_type": "Greet"}},
		}),
	}
	var result string
	if err := wfctx.ExecuteActivity("Greet", []any{"world"}, &result, nil); err != nil {
		t.Fatalf("ExecuteActivity = %v", err)
	}
	if result != "hello, world" {
		t.Fatalf("result = %q, want 'hello, world'", result)
	}
}

func TestExecuteActivitySuspendsWhenActivityStillRunning(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"act-1","namespace":"default","queue":"default","type":"activity:Greet","state":"leased","attempt":1,"lease_timeout_seconds":0,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
	}))
	defer server.Close()

	conn, _ := client.NewConnection(client.ConnectionOptions{Address: server.URL})
	wfctx := &workflowContext{
		Context: context.Background(),
		logger:  slog.Default(),
		conn:    conn,
		replay: replay.New([]client.WorkflowHistoryEvent{
			{Type: replay.EventActivityTaskScheduled, TaskID: "act-1", Attributes: map[string]any{"activity_type": "Greet"}},
		}),
	}
	var ignored string
	err := wfctx.ExecuteActivity("Greet", nil, &ignored, nil)
	if !workflow.IsSuspended(err) {
		t.Fatalf("expected suspend, got %v", err)
	}
}

func TestExecuteActivityRaisesDeterminismOnNameDrift(t *testing.T) {
	t.Parallel()
	wfctx := &workflowContext{
		Context: context.Background(),
		logger:  slog.Default(),
		replay: replay.New([]client.WorkflowHistoryEvent{
			{Type: replay.EventActivityTaskScheduled, TaskID: "act-1", Attributes: map[string]any{"activity_type": "Greet"}},
		}),
	}
	err := wfctx.ExecuteActivity("Farewell", nil, nil, nil)
	if err == nil || !strings.Contains(err.Error(), "activity command changed") {
		t.Fatalf("expected determinism violation, got %v", err)
	}
	if !failure.IsApplication(err) {
		t.Fatalf("determinism violation should surface as Application, got %T", err)
	}
}

func TestCancellationRequestedShortCircuitsCommands(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, []client.WorkflowHistoryEvent{
		{Type: replay.EventWorkflowCancellationRequest},
	})
	if err := wfctx.Sleep(time.Second); !failure.IsCancelled(err) {
		t.Fatalf("expected Cancelled, got %v", err)
	}
	if err := wfctx.ExecuteActivity("Greet", nil, nil, nil); !failure.IsCancelled(err) {
		t.Fatalf("ExecuteActivity expected Cancelled, got %v", err)
	}
	if err := wfctx.ExecuteChildWorkflow("Sub", nil, nil, nil); !failure.IsCancelled(err) {
		t.Fatalf("ExecuteChildWorkflow expected Cancelled, got %v", err)
	}
}

func TestContinueAsNewSentinelFromContext(t *testing.T) {
	t.Parallel()
	wfctx := &workflowContext{
		Context:      context.Background(),
		logger:       slog.Default(),
		workflowID:   "wf-1",
		workflowType: "Greet",
		queue:        "default",
	}
	err := wfctx.ContinueAsNew(workflow.ContinueAsNewOptions{Args: []any{"world"}})
	if !workflow.IsContinueAsNew(err) {
		t.Fatalf("expected continue-as-new sentinel, got %T", err)
	}
}

func TestReplayOnlyContextDoesNotScheduleNewCommands(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, nil)
	wfctx.replayOnly = true
	if err := wfctx.Sleep(time.Second); !workflow.IsSuspended(err) {
		t.Fatalf("Sleep = %v, want replay suspension", err)
	}
	if err := wfctx.ExecuteActivity("Greet", nil, nil, nil); !workflow.IsSuspended(err) {
		t.Fatalf("ExecuteActivity = %v, want replay suspension", err)
	}
	if err := wfctx.ExecuteChildWorkflow("Child", nil, nil, nil); !workflow.IsSuspended(err) {
		t.Fatalf("ExecuteChildWorkflow = %v, want replay suspension", err)
	}
	if err := wfctx.Milestone("ignored", workflow.MilestoneOptions{}); err != nil {
		t.Fatalf("Milestone = %v, want no-op", err)
	}
	if err := wfctx.ContinueAsNew(workflow.ContinueAsNewOptions{}); !workflow.IsSuspended(err) {
		t.Fatalf("ContinueAsNew = %v, want replay suspension", err)
	}
}

func TestSetUpdateHandlerReplaysCompletedUpdates(t *testing.T) {
	t.Parallel()
	wfctx := newReplayCtx(t, []client.WorkflowHistoryEvent{
		{Type: replay.EventWorkflowUpdateCompleted, Attributes: map[string]any{"update_name": "rename", "args": []any{"Ada"}}},
		{Type: replay.EventWorkflowUpdateCompleted, Attributes: map[string]any{"update_name": "rename", "args": []any{"Grace"}}},
	})
	var name string
	err := wfctx.SetUpdateHandler("rename", func(args []any) (any, error) {
		name = args[0].(string)
		return name, nil
	})
	if err != nil {
		t.Fatalf("SetUpdateHandler: %v", err)
	}
	if name != "Grace" {
		t.Fatalf("replayed name = %q, want Grace", name)
	}
}

func TestRunWorkflowBlocksWhenHistoryFetchFails(t *testing.T) {
	t.Parallel()
	var blockHits, historyHits int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.Contains(r.URL.Path, "/history"):
			historyHits++
			http.Error(w, "history boom", http.StatusInternalServerError)
		case strings.Contains(r.URL.Path, "/block"):
			blockHits++
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"id":"wf-task","namespace":"default","queue":"default","type":"workflow:Greet","state":"blocked","attempt":0,"lease_timeout_seconds":0,"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		default:
			http.Error(w, "unexpected request "+r.URL.Path, http.StatusBadRequest)
		}
	}))
	defer server.Close()

	conn, _ := client.NewConnection(client.ConnectionOptions{Address: server.URL, AuthToken: "tok"})
	w, err := New(Options{
		Connection: conn,
		AgentID:    "agent-1",
		Workflows:  workflow.Registry{"Greet": func(ctx workflow.Context, args []any) (any, error) { return "ok", nil }},
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	conn.SeedAgentSession("agent-1", "tok", time.Now().Add(time.Hour))

	res, err := w.runWorkflow(context.Background(), &client.Task{
		ID: "wf-task", Namespace: "default", Queue: "default",
		Type: client.TaskTypePrefixWorkflow + "Greet",
	})
	if !errors.Is(err, errWorkflowAlreadyBlocked) {
		t.Fatalf("err = %v, want errWorkflowAlreadyBlocked", err)
	}
	if res != nil {
		t.Fatalf("result = %+v, want nil", res)
	}
	if historyHits != 1 || blockHits != 1 {
		t.Fatalf("history hits = %d, block hits = %d (want 1/1)", historyHits, blockHits)
	}
}

func TestWorkflowQueryAndUpdateDispatchReplayRegisteredHandlers(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/v1/workflows/run-1":
			_, _ = w.Write([]byte(`{"id":"workflow-1","run_id":"run-1","namespace":"default","type":"Approval","queue":"default","task_id":"workflow-task-1","state":"running","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		case "/api/v1/tasks/workflow-task-1":
			_, _ = w.Write([]byte(`{"id":"workflow-task-1","namespace":"default","queue":"default","type":"workflow:Approval","state":"blocked","attempt":1,"lease_timeout_seconds":30,"payload":{"workflowType":"Approval","workflowId":"workflow-1","runId":"run-1","args":[]},"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
		case "/api/v1/workflows/run-1/history":
			_, _ = w.Write([]byte(`[{"id":"event-1","workflow_id":"workflow-1","type":"WorkflowUpdateCompleted","attributes":{"update_name":"rename","args":["Grace"]},"created_at":"2026-01-01T00:00:00Z"}]`))
		default:
			http.Error(w, "unexpected request "+r.URL.Path, http.StatusBadRequest)
		}
	}))
	defer server.Close()

	conn, err := client.NewConnection(client.ConnectionOptions{Address: server.URL, AuthToken: "management-token"})
	if err != nil {
		t.Fatal(err)
	}
	w, err := New(Options{
		Connection: conn,
		AgentID:    "agent-1",
		Workflows: workflow.Registry{"Approval": func(ctx workflow.Context, _ []any) (any, error) {
			name := ""
			if err := ctx.SetUpdateHandler("rename", func(args []any) (any, error) {
				name = args[0].(string)
				return name, nil
			}); err != nil {
				return nil, err
			}
			if err := ctx.SetQueryHandler("approver", func(_ []any) (any, error) { return name, nil }); err != nil {
				return nil, err
			}
			return nil, ctx.Sleep(time.Hour)
		}},
	})
	if err != nil {
		t.Fatal(err)
	}

	queryPayload, _ := json.Marshal(client.WorkflowQueryPayload{
		WorkflowID: "workflow-1", WorkflowRunID: "run-1", WorkflowType: "Approval",
		QueryName: "approver", Args: json.RawMessage(`[]`),
	})
	queryResult, err := w.runWorkflowQuery(context.Background(), &client.Task{
		ID: "query-task-1", Type: "query:Approval", Namespace: "default", Queue: "default", Payload: queryPayload,
	})
	if err != nil {
		t.Fatalf("runWorkflowQuery: %v", err)
	}
	if queryResult.Value != "Grace" || queryResult.Message != "query completed" {
		t.Fatalf("query result = %#v, want Grace", queryResult)
	}

	updatePayload, _ := json.Marshal(client.WorkflowUpdatePayload{
		WorkflowID: "workflow-1", WorkflowRunID: "run-1", WorkflowType: "Approval",
		UpdateName: "rename", Args: json.RawMessage(`["Linus"]`),
	})
	updateResult, err := w.runWorkflowUpdate(context.Background(), &client.Task{
		ID: "update-task-1", Type: "update:Approval", Namespace: "default", Queue: "default", Payload: updatePayload,
	})
	if err != nil {
		t.Fatalf("runWorkflowUpdate: %v", err)
	}
	if updateResult.Value != "Linus" || updateResult.Message != "update completed" {
		t.Fatalf("update result = %#v, want Linus", updateResult)
	}
}

// newReplayCtx builds a workflowContext suitable for unit tests that don't
// need a live HTTP server. The Connection is a stub that fails any actual
// HTTP call — tests that hit the network path build their own httptest.
func newReplayCtx(t *testing.T, history []client.WorkflowHistoryEvent) *workflowContext {
	t.Helper()
	conn, err := client.NewConnection(client.ConnectionOptions{Address: "http://unused.test"})
	if err != nil {
		t.Fatalf("NewConnection: %v", err)
	}
	return &workflowContext{
		Context:    context.Background(),
		logger:     slog.Default(),
		conn:       conn,
		namespace:  "default",
		queue:      "default",
		taskID:     "wf-task",
		workflowID: "wf-1",
		now:        time.Now().UTC(),
		replay:     replay.New(history),
	}
}
