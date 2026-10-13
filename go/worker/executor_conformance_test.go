package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/postgrip-io/postgrip-agent-sdks/go/internal/transport"
)

// The Worker executor conformance suite runs every generated Worker operation
// through the shared executor against a local recording server.

type recordedRequest struct {
	method, path string
	header       http.Header
	body         []byte
}

type workerRecorder struct {
	mu       sync.Mutex
	requests []recordedRequest
}

func (r *workerRecorder) record(request *http.Request) int {
	body, _ := io.ReadAll(request.Body)
	r.mu.Lock()
	defer r.mu.Unlock()
	r.requests = append(r.requests, recordedRequest{request.Method, request.URL.Path, request.Header.Clone(), body})
	return len(r.requests)
}

func (r *workerRecorder) all() []recordedRequest {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]recordedRequest(nil), r.requests...)
}

func sortedOperationIDs() []openAPIOperationID {
	ids := make([]openAPIOperationID, 0, len(openAPIOperationTable))
	for id := range openAPIOperationTable {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
	return ids
}

func conformanceCall(id openAPIOperationID, key string) (map[string]string, http.Header, any) {
	operation := openAPIOperationTable[id]
	pathParameters := map[string]string{}
	for _, name := range operation.PathParameters {
		pathParameters[name] = "p-" + name
	}
	headers := http.Header{
		"authorization": {"Bearer caller-supplied"},
		"X-Caller":      {"caller"},
	}
	if key != "" {
		headers.Set("Idempotency-Key", key)
	}
	var body any
	if operation.RequestSchema != "" {
		body = map[string]any{"name": "worker", "nested": map[string]any{"value": 1}}
	}
	return pathParameters, headers, body
}

// The contract rule must select exactly the operations Worker's former method
// rule (GET, or any request carrying an idempotency key) selected.
func TestWorkerContractRetryRuleMatchesMethodRule(t *testing.T) {
	for _, id := range sortedOperationIDs() {
		operation := openAPIOperationTable[id]
		for _, key := range []string{"", "key-1"} {
			methodRule := operation.Method == http.MethodGet || key != ""
			if got := transport.RetryEligible(operation, key); got != methodRule {
				t.Errorf("%s key=%q: contract rule %v, method rule %v", id, key, got, methodRule)
			}
		}
	}
}

func TestWorkerOperationsConformToExecutorContract(t *testing.T) {
	for _, id := range sortedOperationIDs() {
		operation := openAPIOperationTable[id]
		required := operation.Idempotency == "required"
		key := ""
		if required {
			key = "key-" + string(id)
		}
		for _, retries := range []bool{false, true} {
			name := string(id) + map[bool]string{false: "/retries-disabled", true: "/retries-enabled"}[retries]
			t.Run(name, func(t *testing.T) {
				recorder := &workerRecorder{}
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					if recorder.record(r) < 3 {
						w.Header().Set("Retry-After", "0")
						w.WriteHeader(http.StatusServiceUnavailable)
						_, _ = io.WriteString(w, `{"code":"BUSY","message":"busy","requestId":"req-busy","details":{"attempt":true}}`)
						return
					}
					_, _ = io.WriteString(w, `{}`)
				}))
				defer server.Close()
				pathParameters, headers, body := conformanceCall(id, key)
				var out json.RawMessage
				err := newTestClient(t, server, retries).OpenAPI().Do(context.Background(), string(id), pathParameters, nil, headers, body, &out)

				requests := recorder.all()
				wantAttempts := 1
				if retries {
					wantAttempts = 3
				}
				if len(requests) != wantAttempts {
					t.Fatalf("attempts = %d, want %d", len(requests), wantAttempts)
				}
				if retries && err != nil {
					t.Fatalf("Do() = %v", err)
				}
				if !retries {
					var apiErr *APIError
					if !errors.As(err, &apiErr) || err.Error() != "postgrip-worker: BUSY (HTTP 503): busy" ||
						apiErr.RequestID != "req-busy" || apiErr.Details["attempt"] != true || apiErr.RetryAfter != 0 {
						t.Fatalf("Do() error = %#v", err)
					}
				}
				for attempt, request := range requests {
					if request.method != operation.Method || request.path != expandedPath(operation.Path, pathParameters) {
						t.Fatalf("attempt %d request = %s %s", attempt+1, request.method, request.path)
					}
					wantAuthorization := []string{"Bearer pgt_test-token"}
					if operation.AuthLane == transport.LanePublic {
						wantAuthorization = nil
					}
					if got := request.header.Values("Authorization"); strings.Join(got, ",") != strings.Join(wantAuthorization, ",") {
						t.Fatalf("attempt %d Authorization = %q, want %q", attempt+1, got, wantAuthorization)
					}
					if got := request.header.Get("Idempotency-Key"); got != key {
						t.Fatalf("attempt %d Idempotency-Key = %q, want %q", attempt+1, got, key)
					}
					if request.header.Get("X-Caller") != "" {
						t.Fatalf("attempt %d forwarded a caller header Worker never sends", attempt+1)
					}
					if request.header.Get("Accept") != "application/json" || !bytes.Equal(request.body, requests[0].body) {
						t.Fatalf("attempt %d Accept=%q body=%s", attempt+1, request.header.Get("Accept"), request.body)
					}
					if (body != nil) != (request.header.Get("Content-Type") == "application/json") {
						t.Fatalf("attempt %d Content-Type = %q", attempt+1, request.header.Get("Content-Type"))
					}
				}
			})
		}
		if required {
			t.Run(string(id)+"/missing-key", func(t *testing.T) {
				recorder := &workerRecorder{}
				server := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) { recorder.record(r) }))
				defer server.Close()
				pathParameters, headers, body := conformanceCall(id, "")
				err := newTestClient(t, server, true).OpenAPI().Do(context.Background(), string(id), pathParameters, nil, headers, body, nil)
				if err == nil || err.Error() != "postgrip-worker: idempotency key must contain 1 to 128 visible ASCII characters" {
					t.Fatalf("Do() error = %v", err)
				}
				if len(recorder.all()) != 0 {
					t.Fatal("request without an idempotency key reached the server")
				}
			})
		}
	}
}

func expandedPath(template string, parameters map[string]string) string {
	for name, value := range parameters {
		template = strings.ReplaceAll(template, "{"+name+"}", value)
	}
	return template
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func jsonResponse(request *http.Request, status int, header http.Header, body string) *http.Response {
	if header == nil {
		header = http.Header{}
	}
	return &http.Response{StatusCode: status, Header: header, Body: io.NopCloser(strings.NewReader(body)), Request: request}
}

func fakeClient(t *testing.T, timeout time.Duration, retries bool, transport roundTripFunc) *Client {
	t.Helper()
	client, err := New(Config{BaseURL: "https://worker.example.test", Token: "pgt_test-token", EnableRetries: retries,
		HTTPClient: &http.Client{Timeout: timeout, Transport: transport}})
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestWorkerRetryAfterAboveThirtySecondsIsCapped(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var attempts []time.Time
		client := fakeClient(t, 0, true, func(r *http.Request) (*http.Response, error) {
			attempts = append(attempts, time.Now())
			if len(attempts) == 1 {
				return jsonResponse(r, http.StatusTooManyRequests, http.Header{"Retry-After": {"120"}}, `{"code":"SLOW_DOWN","message":"later"}`), nil
			}
			return jsonResponse(r, http.StatusOK, nil, `{"id":"worker-1"}`), nil
		})
		if _, err := client.Get(context.Background(), "worker-1"); err != nil {
			t.Fatal(err)
		}
		if len(attempts) != 2 || attempts[1].Sub(attempts[0]) != 30*time.Second {
			t.Fatalf("attempts=%d wait=%s", len(attempts), attempts[len(attempts)-1].Sub(attempts[0]))
		}
	})

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "120")
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()
	_, err := newTestClient(t, server, false).Get(context.Background(), "worker-1")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.RetryAfter != 30*time.Second {
		t.Fatalf("Get() error = %#v", err)
	}
	if got, want := err.Error(), "postgrip-worker: HTTP_ERROR (HTTP 503): Service Unavailable"; got != want {
		t.Fatalf("error text = %q, want %q", got, want)
	}
}

func TestWorkerRedirectPolicyFollowsOnlySameOrigin(t *testing.T) {
	var redirected []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/workers/worker-1" {
			http.Redirect(w, r, "/moved", http.StatusTemporaryRedirect)
			return
		}
		redirected = append(redirected, r.Header.Get("Authorization"))
		_, _ = io.WriteString(w, `{"id":"worker-1"}`)
	}))
	defer server.Close()
	worker, err := newTestClient(t, server, false).Get(context.Background(), "worker-1")
	if err != nil || worker.Id != "worker-1" || len(redirected) != 1 || redirected[0] != "Bearer pgt_test-token" {
		t.Fatalf("Get() = %#v, %v; redirected=%q", worker, err, redirected)
	}
}

func TestWorkerResponseBoundIsFourMiB(t *testing.T) {
	for _, size := range []int{maxResponseBytes, maxResponseBytes + 1} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_, _ = io.WriteString(w, `{"items":[]}`+strings.Repeat(" ", size-len(`{"items":[]}`)))
		}))
		_, err := newTestClient(t, server, false).List(context.Background(), ListWorkersOptions{})
		server.Close()
		if size == maxResponseBytes && err != nil {
			t.Fatalf("bounded response rejected: %v", err)
		}
		if size > maxResponseBytes && (err == nil || err.Error() != "postgrip-worker: response is invalid or too large") {
			t.Fatalf("oversized response error = %v", err)
		}
	}
}

func TestWorkerLifetimeDefaultsDeadlinesAndCustomTimeouts(t *testing.T) {
	waitForCancel := func(r *http.Request) (*http.Response, error) {
		<-r.Context().Done()
		return nil, r.Context().Err()
	}
	t.Run("default 30 seconds", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			_, err := fakeClient(t, 0, false, waitForCancel).Get(context.Background(), "worker-1")
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != 30*time.Second {
				t.Fatalf("elapsed=%s err=%v", time.Since(start), err)
			}
		})
	})
	t.Run("earlier caller deadline wins", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			start := time.Now()
			_, err := fakeClient(t, 0, false, waitForCancel).Get(ctx, "worker-1")
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != time.Second {
				t.Fatalf("elapsed=%s err=%v", time.Since(start), err)
			}
		})
	})
	t.Run("custom 60 second client is not truncated", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			worker, err := fakeClient(t, time.Minute, false, func(r *http.Request) (*http.Response, error) {
				select {
				case <-time.After(45 * time.Second):
					return jsonResponse(r, http.StatusOK, nil, `{"id":"worker-1"}`), nil
				case <-r.Context().Done():
					return nil, r.Context().Err()
				}
			}).Get(context.Background(), "worker-1")
			if err != nil || worker.Id != "worker-1" || time.Since(start) != 45*time.Second {
				t.Fatalf("Get() = %#v, %v after %s", worker, err, time.Since(start))
			}
		})
	})
}
