package client

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
)

type recordedAgentRequest struct {
	method string
	path   string
	header http.Header
}

func agentRecordingServer(t *testing.T, respond func(attempt int, w http.ResponseWriter, r *http.Request)) (*httptest.Server, func() []recordedAgentRequest) {
	t.Helper()
	var mu sync.Mutex
	var requests []recordedAgentRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		requests = append(requests, recordedAgentRequest{method: r.Method, path: r.URL.Path, header: r.Header.Clone()})
		attempt := len(requests)
		mu.Unlock()
		respond(attempt, w, r)
	}))
	t.Cleanup(server.Close)
	return server, func() []recordedAgentRequest {
		mu.Lock()
		defer mu.Unlock()
		return append([]recordedAgentRequest(nil), requests...)
	}
}

func writeJSON(w http.ResponseWriter, status int, body string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(body))
}

// A04: a caller-configured Authorization header must never reach a public
// operation, in any spelling, while it keeps precedence on management lanes.
func TestPublicLaneDropsCallerAuthorization(t *testing.T) {
	for _, name := range []string{"Authorization", "authorization", "AUTHORIZATION"} {
		server, requests := agentRecordingServer(t, func(_ int, w http.ResponseWriter, r *http.Request) {
			if strings.HasSuffix(r.URL.Path, "/namespaces") {
				writeJSON(w, http.StatusOK, `[]`)
				return
			}
			writeJSON(w, http.StatusOK, `{}`)
		})
		conn, err := NewConnection(ConnectionOptions{
			Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt-management",
			Headers: map[string]string{name: "Bearer caller-token"},
		})
		if err != nil {
			t.Fatal(err)
		}
		var out map[string]any
		if err := conn.OpenAPI().Do(context.Background(), "refreshAgentSession", nil, nil, nil, map[string]any{"refreshToken": "pgr"}, &out); err != nil {
			t.Fatalf("%s: refresh: %v", name, err)
		}
		if got := requests()[0].header.Values("Authorization"); len(got) != 0 {
			t.Fatalf("%s: public operation Authorization = %q, want none", name, got)
		}
		if _, err := conn.OpenAPI().ListNamespaces(context.Background()); err != nil {
			t.Fatalf("%s: list namespaces: %v", name, err)
		}
		if got := requests()[1].header.Get("Authorization"); got != "Bearer caller-token" {
			t.Fatalf("%s: management Authorization = %q, want the caller header", name, got)
		}
	}
}

func TestPollGoneIsAShutdownDirective(t *testing.T) {
	for _, body := range []string{``, `not json`, `{"directive":{"type":"drain","reason":"upgrade"}}`} {
		server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
			writeJSON(w, http.StatusGone, body)
		})
		conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true})
		if err != nil {
			t.Fatal(err)
		}
		conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
		out, err := conn.OpenAPI().PollAgentTask(context.Background(), OpenAPIPollAgentTaskQuery{Queue: "default"})
		if err != nil {
			t.Fatalf("body %q: %v", body, err)
		}
		if out.Directive == nil || out.Directive.Type != AgentPollDirectiveTypeShutdown {
			t.Fatalf("body %q: directive = %+v, want shutdown", body, out.Directive)
		}
	}
}

// A long poll's server hold counts against the exchange, so the poll gets
// wait_seconds plus headroom even when the ordinary request timeout is shorter.
func TestLongPollLifetimeOutlivesTheRequestTimeout(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		time.Sleep(1500 * time.Millisecond)
		writeJSON(w, http.StatusOK, `{}`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, RequestTimeout: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
	wait := int64(2)
	if _, err := conn.OpenAPI().PollAgentTask(context.Background(), OpenAPIPollAgentTaskQuery{Queue: "default", WaitSeconds: &wait}); err != nil {
		t.Fatalf("long poll: %v", err)
	}
	if _, err := conn.OpenAPI().GetTask(context.Background(), "task-1"); err == nil {
		t.Fatal("ordinary request outlived its 1s timeout")
	}
}

func TestAgentHTTPErrorCarriesEnvelopeFieldsButNoServerText(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusConflict, `{"code":"BAD\nsecret-token","message":"leak secret-token","requestId":"req-9","details":{"field":"name"}}`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = conn.OpenAPI().ListNamespaces(context.Background())
	var sdkErr *failure.SDKError
	if !errors.As(err, &sdkErr) {
		t.Fatalf("error = %T %v, want *failure.SDKError", err, err)
	}
	if sdkErr.StatusCode != http.StatusConflict || sdkErr.Code != "BAD\nsecret-token" || sdkErr.RequestID != "req-9" || sdkErr.Details["field"] != "name" {
		t.Fatalf("fields = %+v", sdkErr)
	}
	if strings.Contains(err.Error(), "secret-token") || strings.Contains(err.Error(), "\n") {
		t.Fatalf("default text includes server content: %q", err.Error())
	}
	if !strings.Contains(string(sdkErr.ResponseBody), "leak secret-token") {
		t.Fatal("raw response body was not preserved for explicit inspection")
	}
}

func TestAgentRetriesBoundedReadsOnlyWhenEnabled(t *testing.T) {
	for _, enabled := range []bool{false, true} {
		server, requests := agentRecordingServer(t, func(attempt int, w http.ResponseWriter, _ *http.Request) {
			if attempt == 1 {
				w.Header().Set("Retry-After", "0")
				writeJSON(w, http.StatusServiceUnavailable, `{"code":"BUSY","message":"busy"}`)
				return
			}
			writeJSON(w, http.StatusOK, `{"id":"task-1"}`)
		})
		conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt", EnableRetries: enabled})
		if err != nil {
			t.Fatal(err)
		}
		_, err = conn.OpenAPI().GetTask(context.Background(), "task-1")
		if enabled && (err != nil || len(requests()) != 2) {
			t.Fatalf("retries enabled: err=%v attempts=%d, want success after 2", err, len(requests()))
		}
		if !enabled && (err == nil || len(requests()) != 1) {
			t.Fatalf("retries disabled: err=%v attempts=%d, want one failed attempt", err, len(requests()))
		}
	}
}

func TestAgentNeverRetriesSignedTaskActions(t *testing.T) {
	server, requests := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusServiceUnavailable, `{"code":"BUSY","message":"busy"}`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, EnableRetries: true})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
	agentID := "agent-1"
	_, err = conn.OpenAPI().CompleteAgentTask(context.Background(), "task-1", OpenAPICompleteAgentTaskQuery{AgentId: &agentID}, OpenAPICompleteAgentTaskRequestBody{})
	if err == nil || len(requests()) != 1 {
		t.Fatalf("signed task action: err=%v attempts=%d, want one failed attempt", err, len(requests()))
	}
	if got := requests()[0].header.Get("Authorization"); got != "Bearer access" {
		t.Fatalf("agent lane Authorization = %q, want the delegated session", got)
	}
}
