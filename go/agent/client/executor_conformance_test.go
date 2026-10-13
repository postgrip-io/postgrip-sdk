package client

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/agent/failure"
	"github.com/postgrip-io/postgrip-agent-sdks/go/protocol"
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

type capturedAgentRequest struct {
	method   string
	path     string
	rawQuery string
	header   http.Header
	body     []byte
}

// Every generated JSON operation follows its contract annotations: auth lane,
// agent-task-v1 signing over the sent bytes, and retry eligibility. The
// expectations come from the annotations, not from the executor.
func TestEveryAgentOperationFollowsItsContractPolicy(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	for id, operation := range openAPIOperationTable {
		if operation.StreamingRequest || operation.WebSocket {
			continue
		}
		t.Run(string(id), func(t *testing.T) {
			var mu sync.Mutex
			var captured []capturedAgentRequest
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				body, _ := io.ReadAll(r.Body)
				mu.Lock()
				captured = append(captured, capturedAgentRequest{r.Method, r.URL.Path, r.URL.RawQuery, r.Header.Clone(), body})
				attempt := len(captured)
				mu.Unlock()
				if attempt == 1 {
					w.Header().Set("Retry-After", "0")
					writeJSON(w, http.StatusServiceUnavailable, `{"code":"BUSY","message":"busy"}`)
					return
				}
				writeJSON(w, http.StatusOK, `{}`)
			}))
			defer server.Close()
			conn, err := NewConnection(ConnectionOptions{
				Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt-management",
				AgentSigningPrivateKey: base64.StdEncoding.EncodeToString(privateKey), EnableRetries: true,
			})
			if err != nil {
				t.Fatal(err)
			}
			conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
			pathParameters := map[string]string{}
			for _, name := range operation.PathParameters {
				pathParameters[name] = "p-" + name
			}
			var body any
			if operation.RequestSchema != "" {
				body = map[string]any{}
			}
			var out any
			callErr := conn.doOpenAPI(context.Background(), id, pathParameters, url.Values{}, body, &out)

			eligible := operation.Retry == "bounded" && operation.Safety == "read-only" && operation.Signing == ""
			if eligible && (callErr != nil || len(captured) != 2) {
				t.Fatalf("retry-eligible: err=%v attempts=%d, want success after 2", callErr, len(captured))
			}
			if !eligible && (callErr == nil || len(captured) != 1) {
				t.Fatalf("not retry-eligible: err=%v attempts=%d, want one failed attempt", callErr, len(captured))
			}

			request := captured[0]
			authorization := request.header.Values("Authorization")
			switch operation.AuthLane {
			case "public":
				if len(authorization) != 0 {
					t.Fatalf("public Authorization = %q, want none", authorization)
				}
			case "management":
				if len(authorization) != 1 || authorization[0] != "Bearer pgt-management" {
					t.Fatalf("management Authorization = %q", authorization)
				}
			case "agent", "either":
				if len(authorization) != 1 || authorization[0] != "Bearer access" {
					t.Fatalf("%s Authorization = %q, want the delegated session", operation.AuthLane, authorization)
				}
			default:
				t.Fatalf("unexpected auth lane %q", operation.AuthLane)
			}

			signature := request.header.Get(protocol.HeaderAgentSignature)
			if operation.Signing != "agent-task-v1" {
				if signature != "" {
					t.Fatalf("unsigned operation carries signature %q", signature)
				}
				return
			}
			seconds, err := strconv.ParseInt(request.header.Get(protocol.HeaderAgentSignatureTimestamp), 10, 64)
			if err != nil {
				t.Fatalf("signature timestamp: %v", err)
			}
			payload := protocol.AgentRequestSignaturePayload{
				Method: request.method, Path: request.path, Query: request.rawQuery,
				Timestamp: time.Unix(seconds, 0), Body: request.body,
			}
			if !protocol.VerifyAgentRequest(publicKey, payload, signature) {
				t.Fatal("signature does not verify against the sent bytes")
			}
		})
	}
}

// A failed delegated-session refresh is returned at once, not retried: the
// operation itself was never sent.
func TestAgentDoesNotRetryAFailedSessionRefresh(t *testing.T) {
	server, requests := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusUnauthorized, `{"code":"INVALID_REFRESH","message":"revoked"}`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, EnableRetries: true, AgentRefreshToken: "pgr-revoked"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := conn.OpenAPI().GetTask(context.Background(), "task-1"); err == nil {
		t.Fatal("expected the refresh failure")
	}
	if got := requests(); len(got) != 1 || got[0].path != "/api/v1/agent/session/refresh" {
		t.Fatalf("requests = %+v, want one refresh and no retried operation", got)
	}
}

// An explicitly empty configured Authorization header still withholds the
// management bearer, as header presence did before.
func TestEmptyConfiguredAuthorizationWithholdsTheManagementToken(t *testing.T) {
	server, requests := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, `[]`)
	})
	conn, err := NewConnection(ConnectionOptions{
		Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt-management",
		Headers: map[string]string{"Authorization": ""},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := conn.OpenAPI().ListNamespaces(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := requests()[0].header.Get("Authorization"); got != "" {
		t.Fatalf("Authorization = %q, want the empty override, not the management token", got)
	}
}

func TestAgentDecodeFailureKeepsTheRequestContext(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, `{not json`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = conn.OpenAPI().ListNamespaces(context.Background())
	if err == nil || !strings.Contains(err.Error(), "postgrip-agent: decode response from GET /api/v1/namespaces") {
		t.Fatalf("err = %v, want the prior decode message with request context", err)
	}
}

// A failure while reading the body keeps its cause, so callers can still
// detect cancellation with errors.Is.
func TestAgentResponseReadFailureKeepsItsCause(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Content-Length", "100")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":`))
		w.(http.Flusher).Flush()
		select {
		case <-r.Context().Done():
		case <-time.After(5 * time.Second):
		}
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt"})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	_, err = conn.OpenAPI().ListNamespaces(ctx)
	if !errors.Is(err, context.DeadlineExceeded) || !strings.Contains(err.Error(), "read response body") {
		t.Fatalf("err = %v, want the read failure wrapping context.DeadlineExceeded", err)
	}
}

// A caller-supplied http.Client keeps its Timeout as given, even for a long
// poll; only the connection's own client gets long-poll headroom.
func TestCustomHTTPClientTimeoutBoundsTheLongPoll(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		time.Sleep(1500 * time.Millisecond)
		writeJSON(w, http.StatusOK, `{}`)
	})
	conn, err := NewConnection(ConnectionOptions{
		Address: server.URL, InsecureDevelopment: true, HTTPClient: &http.Client{Timeout: time.Second},
	})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
	wait := int64(2)
	if _, err := conn.OpenAPI().PollAgentTask(context.Background(), OpenAPIPollAgentTaskQuery{Queue: "default", WaitSeconds: &wait}); err == nil {
		t.Fatal("long poll outlived the caller's 1s client timeout")
	}
}

// A delegated token that enters the refresh margin during a Retry-After
// backoff is refreshed before the next attempt, which stays on the delegated
// lane.
func TestDelegatedTokenRefreshesDuringRetryBackoff(t *testing.T) {
	refreshed := time.Now().Add(time.Hour).UTC().Format(time.RFC3339)
	operationAttempts := 0
	server, requests := agentRecordingServer(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/agent/session/refresh" {
			writeJSON(w, http.StatusOK, `{"agentId":"agent-1","accessToken":"access-2","refreshToken":"pgr-2","accessExpiresAt":"`+refreshed+`"}`)
			return
		}
		operationAttempts++
		if operationAttempts == 1 {
			w.Header().Set("Retry-After", "3")
			writeJSON(w, http.StatusServiceUnavailable, `{"code":"BUSY","message":"busy"}`)
			return
		}
		writeJSON(w, http.StatusOK, `{"id":"task-1"}`)
	})
	// The token is outside the 30-second refresh margin for the first attempt
	// and inside it after the 3-second backoff.
	conn, err := NewConnection(ConnectionOptions{
		Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt-management", EnableRetries: true,
		AgentAccessToken: "access-1", AgentRefreshToken: "pgr-1", AgentAccessExpiresAt: time.Now().Add(32 * time.Second),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := conn.OpenAPI().GetTask(context.Background(), "task-1"); err != nil {
		t.Fatal(err)
	}
	got := requests()
	if len(got) != 3 || got[1].path != "/api/v1/agent/session/refresh" {
		t.Fatalf("requests = %+v, want operation, refresh, operation", got)
	}
	if first, second := got[0].header.Get("Authorization"), got[2].header.Get("Authorization"); first != "Bearer access-1" || second != "Bearer access-2" {
		t.Fatalf("Authorization = %q then %q, want the delegated token refreshed between attempts", first, second)
	}
}

// Agent decodes every non-empty success body, so a whitespace-only body is
// malformed rather than an empty result.
func TestAgentRejectsWhitespaceOnlySuccessBodies(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, " \n ")
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = conn.OpenAPI().ListNamespaces(context.Background())
	if err == nil || !strings.Contains(err.Error(), "postgrip-agent: decode response from GET /api/v1/namespaces") {
		t.Fatalf("err = %v, want the decode failure", err)
	}
}

// An omitted wait_seconds holds for the contract default, so the poll still
// gets long-poll headroom over a shorter request timeout.
func TestLongPollWithoutWaitSecondsUsesTheContractDefault(t *testing.T) {
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		time.Sleep(1500 * time.Millisecond)
		writeJSON(w, http.StatusOK, `{}`)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, RequestTimeout: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	conn.SeedAgentSession("agent-1", "access", time.Now().Add(time.Hour))
	if _, err := conn.OpenAPI().PollAgentTask(context.Background(), OpenAPIPollAgentTaskQuery{Queue: "default"}); err != nil {
		t.Fatalf("long poll without wait_seconds: %v", err)
	}
}

// The same-origin policy returns a cross-origin redirect unfollowed, and
// Agent treats that response as a non-error, as it did before the executor.
func TestAgentUnfollowedRedirectIsNotAnError(t *testing.T) {
	var followed bool
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		followed = true
		writeJSON(w, http.StatusOK, `[]`)
	}))
	defer target.Close()
	server, _ := agentRecordingServer(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Location", target.URL+"/api/v1/namespaces")
		w.WriteHeader(http.StatusFound)
	})
	conn, err := NewConnection(ConnectionOptions{Address: server.URL, InsecureDevelopment: true, AuthToken: "pgt"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := conn.OpenAPI().ListNamespaces(context.Background()); err != nil {
		t.Fatalf("unfollowed redirect: %v", err)
	}
	if followed {
		t.Fatal("cross-origin redirect was followed")
	}
}
