package worker

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow"
)

func TestContinueAsNewDispatch(t *testing.T) {
	for _, scenario := range []string{"defaults", "explicit", "enqueue failure", "completion redelivery"} {
		t.Run(scenario, func(t *testing.T) {
			var enqueues []client.EnqueueTaskRequest
			var keys []string
			var completions []client.CompleteTaskRequest
			var order []string
			server := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, r *http.Request) {
				rw.Header().Set("Content-Type", "application/json")
				switch {
				case strings.HasSuffix(r.URL.Path, "/history"):
					_, _ = io.WriteString(rw, `{"items":[]}`)
				case strings.HasSuffix(r.URL.Path, "/events"):
					_, _ = io.WriteString(rw, `{}`)
				case r.Method == "POST" && r.URL.Path == "/api/v1/tasks":
					var req client.EnqueueTaskRequest
					if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
						t.Error(err)
					}
					enqueues = append(enqueues, req)
					keys = append(keys, r.Header.Get("Idempotency-Key"))
					order = append(order, "enqueue")
					if scenario == "enqueue failure" {
						rw.WriteHeader(http.StatusServiceUnavailable)
						_, _ = io.WriteString(rw, `{"message":"unavailable"}`)
						return
					}
					_, _ = io.WriteString(rw, `{"id":"successor-task","namespace":"ns","queue":"queue","type":"workflow:Next","state":"queued"}`)
				case strings.HasSuffix(r.URL.Path, "/complete"):
					var req client.CompleteTaskRequest
					if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
						t.Error(err)
					}
					completions = append(completions, req)
					order = append(order, "complete")
					if scenario == "completion redelivery" && len(completions) == 1 {
						rw.WriteHeader(http.StatusServiceUnavailable)
						_, _ = io.WriteString(rw, `{"message":"unavailable"}`)
						return
					}
					_, _ = io.WriteString(rw, `{"id":"current-task","state":"succeeded"}`)
				default:
					t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
					rw.WriteHeader(http.StatusBadRequest)
				}
			}))
			defer server.Close()
			conn, err := client.NewConnection(client.ConnectionOptions{Address: server.URL, InsecureDevelopment: true})
			if err != nil {
				t.Fatal(err)
			}
			conn.SeedAgentSession("agent-1", "fixture-token", time.Now().Add(time.Hour))
			opts := workflow.ContinueAsNewOptions{Args: []any{map[string]any{"offset": 42}}, LeaseTimeoutSeconds: 45, WorkflowRunTimeoutMs: 90000, Retry: &workflow.RetryPolicy{MaximumAttempts: 3}}
			wantType, wantQueue := "Current", "queue"
			if scenario == "explicit" {
				opts.WorkflowID, opts.WorkflowType, opts.TaskQueue = "explicit-next", "Next", "other-queue"
				wantType, wantQueue = "Next", "other-queue"
			}
			worker, err := New(Options{Connection: conn, AgentID: "agent-1", Logger: slog.New(slog.NewTextHandler(io.Discard, nil)), Workflows: workflow.Registry{
				"Current": func(ctx workflow.Context, _ []any) (any, error) { return nil, ctx.ContinueAsNew(opts) },
			}})
			if err != nil {
				t.Fatal(err)
			}
			task := &client.Task{ID: "current-task", Namespace: "ns", Queue: "queue", Type: "workflow:Current", LeaseTimeoutSeconds: 30, Payload: json.RawMessage(`{"workflowId":"old-workflow","workflowType":"Current","args":[]}`)}
			worker.handleTask(context.Background(), task)
			if len(enqueues) != 1 {
				t.Fatalf("enqueue count = %d, want 1; completions=%+v", len(enqueues), completions)
			}
			if scenario == "enqueue failure" {
				if len(completions) != 0 {
					t.Fatal("completed despite failed enqueue")
				}
				return
			}
			if scenario == "completion redelivery" {
				task.Attempt++
				worker.handleTask(context.Background(), task)
				if len(enqueues) != 2 || keys[0] != keys[1] || !reflect.DeepEqual(enqueues[0], enqueues[1]) {
					t.Fatalf("redelivery changed enqueue identity/body: keys=%v requests=%+v", keys, enqueues)
				}
			}
			if keys[0] == "" || len(keys[0]) > 128 {
				t.Fatalf("invalid idempotency key %q", keys[0])
			}
			var payload client.WorkflowPayload
			if err := json.Unmarshal(enqueues[0].Payload, &payload); err != nil {
				t.Fatal(err)
			}
			if payload.WorkflowID == "" || payload.WorkflowID == "old-workflow" {
				t.Fatalf("successor ID = %q", payload.WorkflowID)
			}
			if scenario == "explicit" && payload.WorkflowID != "explicit-next" {
				t.Fatalf("explicit ID = %q", payload.WorkflowID)
			}
			if payload.WorkflowType != wantType || payload.ContinuedFromWorkflowID != "old-workflow" || payload.Namespace != "ns" || payload.RunTimeoutMs != 90000 || !reflect.DeepEqual(payload.RetryPolicy, opts.Retry) || string(payload.Args) != `[{"offset":42}]` {
				t.Fatalf("successor payload = %+v", payload)
			}
			req := enqueues[0]
			if req.Namespace != "ns" || req.Queue != wantQueue || req.Type != "workflow:"+wantType || req.LeaseTimeoutSeconds != 45 {
				t.Fatalf("enqueue = %+v", req)
			}
			if len(completions) != len(enqueues) {
				t.Fatalf("completion count = %d", len(completions))
			}
			for i, completion := range completions {
				can := completion.Result.ContinueAsNew
				if can == nil || can.TaskID != "successor-task" || can.WorkflowID != payload.WorkflowID || can.WorkflowType != wantType || can.TaskQueue != wantQueue {
					t.Fatalf("continuation = %+v", can)
				}
				if order[2*i] != "enqueue" || order[2*i+1] != "complete" {
					t.Fatalf("order = %v", order)
				}
			}
		})
	}
}
