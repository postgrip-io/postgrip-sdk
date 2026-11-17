package worker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/client"
	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/workflow"
)

func TestExecuteActivityStartToCloseTimeout(t *testing.T) {
	for _, tt := range []struct {
		name    string
		opts    *workflow.ActivityOptions
		seconds int
	}{
		{"defaults", nil, 0},
		{"lease fallback", &workflow.ActivityOptions{LeaseTimeoutSeconds: 45}, 45},
		{"four hours", &workflow.ActivityOptions{StartToCloseMs: 14400000}, 14400},
		{"fraction rounded up", &workflow.ActivityOptions{StartToCloseMs: 1001}, 2},
		{"minimum positive", &workflow.ActivityOptions{StartToCloseMs: 1}, 1},
		{"explicit activity timeout wins", &workflow.ActivityOptions{StartToCloseMs: 30000, LeaseTimeoutSeconds: 60}, 30},
	} {
		t.Run(tt.name, func(t *testing.T) {
			var requests []client.EnqueueTaskRequest
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != "POST" || r.URL.Path != "/api/v1/tasks" {
					t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
				}
				var req client.EnqueueTaskRequest
				if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
					t.Error(err)
				}
				requests = append(requests, req)
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(`{"id":"activity-1","namespace":"default","queue":"default","type":"activity:ReindexCollection","state":"queued"}`))
			}))
			defer srv.Close()
			conn, err := client.NewConnection(client.ConnectionOptions{Address: srv.URL, InsecureDevelopment: true})
			if err != nil {
				t.Fatal(err)
			}
			conn.SeedAgentSession("agent-1", "fixture-session", time.Now().Add(time.Hour))
			ctx := &workflowContext{Context: context.Background(), conn: conn, namespace: "default", queue: "default", taskID: "task-1", workflowID: "workflow-1"}
			if err := ctx.ExecuteActivity("ReindexCollection", []any{"docs"}, nil, tt.opts); !workflow.IsSuspended(err) {
				t.Fatalf("expected suspension, got %v", err)
			}
			if len(requests) != 1 {
				t.Fatalf("enqueue count=%d", len(requests))
			}
			if got := requests[0].LeaseTimeoutSeconds; got != tt.seconds {
				t.Fatalf("activity timeout=%d seconds, want %d", got, tt.seconds)
			}
		})
	}
}
