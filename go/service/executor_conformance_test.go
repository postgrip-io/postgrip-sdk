package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
	"testing/synctest"
	"time"
)

// The Service executor conformance suite runs every generated Service
// operation against a local recording server. Its expectations are derived
// from the contract annotations and the generated typed bindings, not from the
// executor, so the suite also runs against the pre-executor Service transport.

type conformanceRequest struct {
	method, path string
	header       http.Header
	body         []byte
}

type conformanceRecorder struct {
	mu       sync.Mutex
	requests []conformanceRequest
}

func (r *conformanceRecorder) record(request *http.Request) int {
	body, _ := io.ReadAll(request.Body)
	r.mu.Lock()
	defer r.mu.Unlock()
	r.requests = append(r.requests, conformanceRequest{request.Method, request.URL.Path, request.Header.Clone(), body})
	return len(r.requests)
}

func (r *conformanceRecorder) all() []conformanceRequest {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]conformanceRequest(nil), r.requests...)
}

func sortedServiceOperationIDs() []openAPIOperationID {
	ids := make([]openAPIOperationID, 0, len(openAPIOperationTable))
	for id := range openAPIOperationTable {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
	return ids
}

// ifMatchOperations returns the operations whose generated typed binding takes
// an If-Match header, which the generator emits only where the contract
// declares that header parameter.
func ifMatchOperations(t *testing.T) map[openAPIOperationID]bool {
	t.Helper()
	declared := map[openAPIOperationID]bool{}
	client := reflect.TypeOf(&OpenAPIClient{})
	for index := 0; index < client.NumMethod(); index++ {
		method := client.Method(index)
		id := openAPIOperationID(strings.ToLower(method.Name[:1]) + method.Name[1:])
		if _, ok := openAPIOperationTable[id]; !ok {
			continue
		}
		for parameter := 1; parameter < method.Type.NumIn(); parameter++ {
			input := method.Type.In(parameter)
			if input.Kind() != reflect.Struct || !strings.HasSuffix(input.Name(), "Headers") {
				continue
			}
			if _, ok := input.FieldByName("IfMatch"); ok {
				declared[id] = true
			}
		}
	}
	if len(declared) == 0 {
		t.Fatal("no generated Service binding declares If-Match")
	}
	return declared
}

func conformanceClient(t *testing.T, server *httptest.Server, configure func(*Config)) *Client {
	t.Helper()
	config := Config{BaseURL: server.URL, Token: "pgt_test-token", InsecureDevelopment: true}
	if configure != nil {
		configure(&config)
	}
	client, err := New(config)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func serviceConformanceCall(id openAPIOperationID, key string) (map[string]string, http.Header, any) {
	operation := openAPIOperationTable[id]
	pathParameters := map[string]string{}
	for _, name := range operation.PathParameters {
		pathParameters[name] = "p-" + name
	}
	headers := http.Header{
		"authorization": {"Bearer caller-supplied"},
		"X-Caller":      {"caller"},
		"If-Match":      {`"etag:1"`},
	}
	if key != "" {
		headers.Set("Idempotency-Key", key)
	}
	var body any
	if operation.RequestSchema != "" {
		body = map[string]any{"name": "service", "nested": map[string]any{"value": 1}}
	}
	return pathParameters, headers, body
}

func expandedServicePath(template string, parameters map[string]string) string {
	for name, value := range parameters {
		template = strings.ReplaceAll(template, "{"+name+"}", value)
	}
	return template
}

func TestServiceOperationsConformToExecutorContract(t *testing.T) {
	ifMatch := ifMatchOperations(t)
	for _, id := range sortedServiceOperationIDs() {
		operation := openAPIOperationTable[id]
		if operation.AuthLane != "service-management" {
			t.Fatalf("%s: unexpected Service auth lane %q", id, operation.AuthLane)
		}
		required := operation.Idempotency == "required"
		key := ""
		if required {
			key = "key-" + string(id)
		}
		for _, retries := range []bool{false, true} {
			name := string(id) + map[bool]string{false: "/retries-disabled", true: "/retries-enabled"}[retries]
			t.Run(name, func(t *testing.T) {
				recorder := &conformanceRecorder{}
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
				pathParameters, headers, body := serviceConformanceCall(id, key)
				var out json.RawMessage
				err := conformanceClient(t, server, func(config *Config) { config.EnableRetries = retries }).
					OpenAPI().Do(context.Background(), string(id), pathParameters, nil, headers, body, &out)

				// The contract rule: bounded retry for read-only operations or
				// those carrying an idempotency key, only when enabled.
				eligible := operation.Retry == "bounded" && (operation.Safety == "read-only" || key != "")
				wantAttempts := 1
				if retries && eligible {
					wantAttempts = 3
				}
				requests := recorder.all()
				if len(requests) != wantAttempts {
					t.Fatalf("attempts = %d, want %d", len(requests), wantAttempts)
				}
				if wantAttempts == 3 && (err != nil || string(out) != `{}`) {
					t.Fatalf("Do() = %s, %v", out, err)
				}
				if wantAttempts == 1 {
					var apiErr *APIError
					if !errors.As(err, &apiErr) || err.Error() != "postgrip-service: BUSY (HTTP 503): busy" ||
						apiErr.StatusCode != http.StatusServiceUnavailable || apiErr.Code != "BUSY" || apiErr.Message != "busy" ||
						apiErr.RequestID != "req-busy" || apiErr.Details["attempt"] != true || apiErr.RetryAfter != 0 {
						t.Fatalf("Do() error = %#v", err)
					}
				}
				for attempt, request := range requests {
					if request.method != operation.Method || request.path != expandedServicePath(operation.Path, pathParameters) {
						t.Fatalf("attempt %d request = %s %s", attempt+1, request.method, request.path)
					}
					// The Service management bearer replaces a caller-supplied Authorization.
					if got := request.header.Values("Authorization"); len(got) != 1 || got[0] != "Bearer pgt_test-token" {
						t.Fatalf("attempt %d Authorization = %q", attempt+1, got)
					}
					if got := request.header.Get("Idempotency-Key"); got != key {
						t.Fatalf("attempt %d Idempotency-Key = %q, want %q", attempt+1, got, key)
					}
					if got := request.header.Get("X-Caller"); got != "caller" {
						t.Fatalf("attempt %d X-Caller = %q; Service forwards caller headers", attempt+1, got)
					}
					wantIfMatch := []string(nil)
					if ifMatch[id] {
						wantIfMatch = []string{`"etag:1"`}
					}
					if got := request.header.Values("If-Match"); !reflect.DeepEqual(got, wantIfMatch) {
						t.Fatalf("attempt %d If-Match = %q, want %q", attempt+1, got, wantIfMatch)
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
			for _, invalid := range []struct{ key, message string }{
				{"", "postgrip-service: idempotency key must contain 1 to 128 visible ASCII characters"},
				{"bad key", "postgrip-service: idempotency key must contain visible ASCII only"},
			} {
				t.Run(string(id)+"/rejects-key-"+map[bool]string{true: "missing", false: "invalid"}[invalid.key == ""], func(t *testing.T) {
					recorder := &conformanceRecorder{}
					server := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) { recorder.record(r) }))
					defer server.Close()
					pathParameters, headers, body := serviceConformanceCall(id, invalid.key)
					err := conformanceClient(t, server, func(config *Config) { config.EnableRetries = true }).
						OpenAPI().Do(context.Background(), string(id), pathParameters, nil, headers, body, nil)
					if err == nil || err.Error() != invalid.message {
						t.Fatalf("Do() error = %v", err)
					}
					if len(recorder.all()) != 0 {
						t.Fatal("request without a valid idempotency key reached the server")
					}
				})
			}
		}
	}
}

func TestServiceErrorEnvelopeFallbacksKeepText(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-Request-ID", "request-header")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = io.WriteString(w, "not an envelope")
	}))
	defer server.Close()
	_, err := conformanceClient(t, server, nil).Resolve(context.Background(), "api")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != "HTTP_ERROR" || apiErr.Message != "Bad Gateway" ||
		apiErr.RequestID != "request-header" || apiErr.Details != nil {
		t.Fatalf("Resolve() error = %#v", err)
	}
	if got, want := err.Error(), "postgrip-service: HTTP_ERROR (HTTP 502): Bad Gateway"; got != want {
		t.Fatalf("error text = %q, want %q", got, want)
	}
	keyed := APIError{StatusCode: 500, Message: "boom"}
	if got, want := keyed.Error(), "postgrip-service: HTTP 500: boom"; got != want {
		t.Fatalf("code-less error text = %q, want %q", got, want)
	}
}

func TestServiceRedirectPolicyFollowsOnlySameOrigin(t *testing.T) {
	var destinationCalls int
	destination := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		destinationCalls++
		_, _ = io.WriteString(w, `{}`)
	}))
	defer destination.Close()
	var redirected []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/services/resolve":
			http.Redirect(w, r, "/moved", http.StatusTemporaryRedirect)
		case "/api/v1/services/apps":
			http.Redirect(w, r, destination.URL+"/api/v1/services/apps", http.StatusTemporaryRedirect)
		default:
			redirected = append(redirected, r.Header.Get("Authorization"))
			_, _ = io.WriteString(w, `{"moved":true}`)
		}
	}))
	defer server.Close()
	client := conformanceClient(t, server, nil)

	var out json.RawMessage
	err := client.OpenAPI().Do(context.Background(), "resolveService", nil, nil, nil, nil, &out)
	if err != nil || string(out) != `{"moved":true}` || len(redirected) != 1 || redirected[0] != "Bearer pgt_test-token" {
		t.Fatalf("same-origin redirect = %s, %v; redirected=%q", out, err, redirected)
	}
	err = client.OpenAPI().Do(context.Background(), "listServiceApps", nil, nil, nil, nil, &out)
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusTemporaryRedirect || destinationCalls != 0 {
		t.Fatalf("cross-origin redirect error = %#v, destination calls = %d", err, destinationCalls)
	}
}

func paddedJSON(size int) string {
	const prefix, suffix = `{"contentType":"image/png","dataBase64":"`, `"}`
	return prefix + strings.Repeat("A", size-len(prefix)-len(suffix)) + suffix
}

func TestServiceResponseBoundsApplyScreenshotOverrideToSuccessOnly(t *testing.T) {
	tooLarge := "postgrip-service: response is invalid or too large"
	pathParameters := map[string]string{"serviceId": "project-1", "deploymentId": "deployment-1"}
	for _, test := range []struct {
		name      string
		operation string
		status    int
		size      int
		wantErr   string
	}{
		{"ordinary at bound", "resolveService", http.StatusOK, maxResponseBytes, ""},
		{"ordinary over bound", "resolveService", http.StatusOK, maxResponseBytes + 1, tooLarge},
		{"ordinary error over bound", "resolveService", http.StatusInternalServerError, maxResponseBytes + 1, tooLarge},
		{"screenshot over ordinary bound", "getServiceDeploymentScreenshot", http.StatusOK, maxResponseBytes + 1, ""},
		{"screenshot at override", "getServiceDeploymentScreenshot", http.StatusOK, maxScreenshotResponseBytes, ""},
		{"screenshot over override", "getServiceDeploymentScreenshot", http.StatusOK, maxScreenshotResponseBytes + 1, tooLarge},
		{"screenshot error at bound", "getServiceDeploymentScreenshot", http.StatusInternalServerError, maxResponseBytes,
			"postgrip-service: HTTP_ERROR (HTTP 500): Internal Server Error"},
		{"screenshot error over bound", "getServiceDeploymentScreenshot", http.StatusInternalServerError, maxResponseBytes + 1, tooLarge},
	} {
		t.Run(test.name, func(t *testing.T) {
			payload := paddedJSON(test.size)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(test.status)
				_, _ = io.WriteString(w, payload)
			}))
			defer server.Close()
			var parameters map[string]string
			if test.operation == "getServiceDeploymentScreenshot" {
				parameters = pathParameters
			}
			var out json.RawMessage
			err := conformanceClient(t, server, nil).OpenAPI().Do(context.Background(), test.operation, parameters, nil, nil, nil, &out)
			if test.wantErr == "" {
				if err != nil || len(out) != test.size {
					t.Fatalf("Do() = %d bytes, %v", len(out), err)
				}
				return
			}
			if err == nil || err.Error() != test.wantErr {
				t.Fatalf("Do() error = %v, want %q", err, test.wantErr)
			}
		})
	}
}

type serviceRoundTripFunc func(*http.Request) (*http.Response, error)

func (f serviceRoundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func serviceJSONResponse(request *http.Request, status int, header http.Header, body string) *http.Response {
	if header == nil {
		header = http.Header{}
	}
	return &http.Response{StatusCode: status, Header: header, Body: io.NopCloser(strings.NewReader(body)), Request: request}
}

func fakeServiceClient(t *testing.T, timeout time.Duration, configure func(*Config), transport serviceRoundTripFunc) *Client {
	t.Helper()
	config := Config{BaseURL: "https://service.example.test", Token: "pgt_test-token",
		HTTPClient: &http.Client{Timeout: timeout, Transport: transport}}
	if configure != nil {
		configure(&config)
	}
	client, err := New(config)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestServiceRetryAfterCeilingIsConfigurable(t *testing.T) {
	for _, test := range []struct {
		name       string
		ceiling    time.Duration
		status     int
		retryAfter string
		wantWait   time.Duration
		jittered   bool
	}{
		{"default ceiling caps at 30 seconds", 0, http.StatusTooManyRequests, "120", 30 * time.Second, false},
		{"configured ceiling caps lower", 5 * time.Second, http.StatusServiceUnavailable, "120", 5 * time.Second, false},
		{"value under the ceiling is honored", 5 * time.Second, http.StatusServiceUnavailable, "3", 3 * time.Second, false},
		{"zero retries without backoff", 0, http.StatusServiceUnavailable, "0", 0, false},
		{"overflowing value caps at the ceiling", 0, http.StatusServiceUnavailable, strings.Repeat("9", 100), 30 * time.Second, false},
		{"signed value is not delta-seconds", 0, http.StatusServiceUnavailable, "+5", 0, true},
		{"ignored outside 429 and 503", 0, http.StatusBadGateway, "120", 0, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				var attempts []time.Time
				client := fakeServiceClient(t, 0, func(config *Config) {
					config.EnableRetries = true
					config.RetryAfterMaxDelay = test.ceiling
				}, func(r *http.Request) (*http.Response, error) {
					attempts = append(attempts, time.Now())
					if len(attempts) == 1 {
						return serviceJSONResponse(r, test.status, http.Header{"Retry-After": {test.retryAfter}}, `{"code":"SLOW_DOWN","message":"later"}`), nil
					}
					return serviceJSONResponse(r, http.StatusOK, nil, `{}`), nil
				})
				var out json.RawMessage
				if err := client.OpenAPI().Do(context.Background(), "resolveService", nil, nil, nil, nil, &out); err != nil {
					t.Fatal(err)
				}
				if len(attempts) != 2 {
					t.Fatalf("attempts = %d", len(attempts))
				}
				wait := attempts[1].Sub(attempts[0])
				// The first jittered backoff is below 200 milliseconds.
				if test.jittered && wait >= 200*time.Millisecond || !test.jittered && wait != test.wantWait {
					t.Fatalf("wait = %s, want %s (jittered %v)", wait, test.wantWait, test.jittered)
				}
			})
		})
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "120")
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()
	_, err := conformanceClient(t, server, func(config *Config) { config.RetryAfterMaxDelay = 5 * time.Second }).
		Resolve(context.Background(), "api")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.RetryAfter != 5*time.Second {
		t.Fatalf("Resolve() error = %#v", err)
	}
	if got, want := err.Error(), "postgrip-service: HTTP_ERROR (HTTP 503): Service Unavailable"; got != want {
		t.Fatalf("error text = %q, want %q", got, want)
	}
}

func TestServiceLifetimeDefaultsDeadlinesAndCustomTimeouts(t *testing.T) {
	waitForCancel := func(r *http.Request) (*http.Response, error) {
		<-r.Context().Done()
		return nil, r.Context().Err()
	}
	t.Run("default 30 seconds", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			_, err := fakeServiceClient(t, 0, nil, waitForCancel).Resolve(context.Background(), "api")
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
			_, err := fakeServiceClient(t, 0, nil, waitForCancel).Resolve(ctx, "api")
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) != time.Second {
				t.Fatalf("elapsed=%s err=%v", time.Since(start), err)
			}
		})
	})
	t.Run("custom 60 second client is not truncated", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			var out json.RawMessage
			err := fakeServiceClient(t, time.Minute, nil, func(r *http.Request) (*http.Response, error) {
				select {
				case <-time.After(45 * time.Second):
					return serviceJSONResponse(r, http.StatusOK, nil, `{"id":"service-1"}`), nil
				case <-r.Context().Done():
					return nil, r.Context().Err()
				}
			}).OpenAPI().Do(context.Background(), "resolveService", nil, nil, nil, nil, &out)
			if err != nil || string(out) != `{"id":"service-1"}` || time.Since(start) != 45*time.Second {
				t.Fatalf("Do() = %s, %v after %s", out, err, time.Since(start))
			}
		})
	})
}
