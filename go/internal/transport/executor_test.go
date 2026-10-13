package transport

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

// recorded is one request seen by the local recording server.
type recorded struct {
	method string
	path   string
	header http.Header
	body   []byte
}

type recorder struct {
	mu       sync.Mutex
	requests []recorded
}

func (r *recorder) add(request *http.Request) {
	body, _ := io.ReadAll(request.Body)
	r.mu.Lock()
	defer r.mu.Unlock()
	r.requests = append(r.requests, recorded{request.Method, request.URL.RequestURI(), request.Header.Clone(), body})
}

func (r *recorder) all() []recorded {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]recorded(nil), r.requests...)
}

// recordingServer answers each request with the next scripted response and
// repeats the last one when the script runs out.
func recordingServer(t *testing.T, responses ...func(http.ResponseWriter)) (*httptest.Server, *recorder) {
	t.Helper()
	rec := &recorder{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec.add(r)
		index := min(len(rec.all())-1, len(responses)-1)
		responses[index](w)
	}))
	t.Cleanup(server.Close)
	return server, rec
}

func status(code int, headers map[string]string, body string) func(http.ResponseWriter) {
	return func(w http.ResponseWriter) {
		for name, value := range headers {
			w.Header().Set(name, value)
		}
		w.WriteHeader(code)
		_, _ = io.WriteString(w, body)
	}
}

func testExecutor(t *testing.T, server *httptest.Server) *Executor {
	t.Helper()
	baseURL, err := url.Parse(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	return &Executor{
		Plane: "test", BaseURL: baseURL, HTTPClient: HTTPClient(server.Client()),
		Credentials: Credentials{ManagementToken: "management-token"},
		Retry:       RetryConfig{MaxAttempts: 3, RetryAfterMax: 30 * time.Second},
	}
}

func operation(lane, safety, idempotency string) Operation {
	method := http.MethodGet
	if safety != "read-only" {
		method = http.MethodPost
	}
	return Operation{ID: "testOperation", Method: method, Path: "/api/v1/test", AuthLane: lane,
		Safety: safety, Idempotency: idempotency, Pagination: "none", Retry: "bounded"}
}

func TestExecutorAppliesCredentialsByAuthLane(t *testing.T) {
	callerHeaders := []http.Header{
		nil,
		{"Authorization": {"Bearer caller"}},
		{"authorization": {"Bearer caller"}},
		{"AUTHORIZATION": {"Bearer caller"}},
	}
	tests := []struct {
		lane, want  string
		hasSession  bool
		wantRefresh int
		// callerWins marks lanes where a caller-supplied header keeps precedence.
		callerWins bool
	}{
		{lane: LanePublic, want: ""},
		{lane: LaneManagement, want: "Bearer management-token", callerWins: true},
		{lane: LaneWorkerManagement, want: "Bearer management-token", callerWins: true},
		{lane: LaneServiceManagement, want: "Bearer management-token", callerWins: true},
		{lane: LaneAgent, want: "Bearer delegated-1", hasSession: true, wantRefresh: 1},
		{lane: LaneEither, want: "Bearer delegated-1", hasSession: true, wantRefresh: 1},
		{lane: LaneEither, want: "Bearer management-token", hasSession: false, callerWins: true},
	}
	for _, test := range tests {
		for _, header := range callerHeaders {
			server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
			executor := testExecutor(t, server)
			refreshes := 0
			executor.Credentials.HasDelegated = func() bool { return test.hasSession }
			executor.Credentials.Delegated = func(context.Context) (string, error) {
				refreshes++
				return "delegated-" + string(rune('0'+refreshes)), nil
			}
			if _, err := executor.Do(context.Background(), Call{Operation: operation(test.lane, "read-only", "none"), Header: header}, nil); err != nil {
				t.Fatalf("%s: %v", test.lane, err)
			}
			want := test.want
			if test.callerWins && header != nil {
				want = "Bearer caller"
			}
			got := rec.all()[0].header.Values("Authorization")
			if (want == "" && len(got) != 0) || (want != "" && (len(got) != 1 || got[0] != want)) {
				t.Fatalf("%s with caller %v: Authorization = %q, want %q", test.lane, header, got, want)
			}
			if refreshes != test.wantRefresh {
				t.Fatalf("%s: credential hook calls = %d, want %d", test.lane, refreshes, test.wantRefresh)
			}
		}
	}
}

func TestExecutorCallsCredentialHookBeforeEveryAttemptOnTheFixedLane(t *testing.T) {
	server, rec := recordingServer(t,
		status(http.StatusServiceUnavailable, map[string]string{"Retry-After": "0"}, `{}`),
		status(http.StatusServiceUnavailable, map[string]string{"Retry-After": "0"}, `{}`),
		status(http.StatusOK, nil, `{}`))
	executor := testExecutor(t, server)
	executor.Retry.Enabled = true
	sessionAvailable := true
	refreshes := 0
	executor.Credentials.HasDelegated = func() bool { return sessionAvailable }
	executor.Credentials.Delegated = func(context.Context) (string, error) {
		refreshes++
		sessionAvailable = false // a later lane decision would now pick management
		return "session-" + string(rune('0'+refreshes)), nil
	}
	if _, err := executor.Do(context.Background(), Call{Operation: operation(LaneEither, "read-only", "none")}, nil); err != nil {
		t.Fatal(err)
	}
	requests := rec.all()
	if len(requests) != 3 {
		t.Fatalf("attempts = %d", len(requests))
	}
	for index, request := range requests {
		if got, want := request.header.Get("Authorization"), "Bearer session-"+string(rune('1'+index)); got != want {
			t.Fatalf("attempt %d Authorization = %q, want %q", index+1, got, want)
		}
	}
}

func TestExecutorAgentLaneRequiresCredentialHook(t *testing.T) {
	server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
	if _, err := testExecutor(t, server).Do(context.Background(), Call{Operation: operation(LaneAgent, "read-only", "none")}, nil); err == nil {
		t.Fatal("agent lane without a credential hook was sent")
	}
	if len(rec.all()) != 0 {
		t.Fatal("request reached the server")
	}
}

func TestExecutorOverrideCallerAuthorizationOnManagementLanes(t *testing.T) {
	for _, lane := range []string{LaneManagement, LaneWorkerManagement, LaneServiceManagement, LaneEither, LanePublic} {
		for _, header := range []http.Header{{"Authorization": {"Bearer caller"}}, {"authorization": {"Bearer caller"}}} {
			server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
			executor := testExecutor(t, server)
			executor.OverrideCallerAuthorization = true
			if _, err := executor.Do(context.Background(), Call{Operation: operation(lane, "read-only", "none"), Header: header}, nil); err != nil {
				t.Fatalf("%s: %v", lane, err)
			}
			want := []string{"Bearer management-token"}
			if lane == LanePublic {
				want = nil
			}
			if got := rec.all()[0].header.Values("Authorization"); strings.Join(got, ",") != strings.Join(want, ",") {
				t.Fatalf("%s with caller %v: Authorization = %q, want %q", lane, header, got, want)
			}
		}
	}
}

func TestExecutorForwardsIfMatchOnlyWhereDeclared(t *testing.T) {
	for _, declared := range [][]string{nil, {"Idempotency-Key"}, {"Idempotency-Key", "If-Match"}, {"if-match"}} {
		for _, header := range []http.Header{{"If-Match": {`"etag:1"`}}, {"if-match": {`"etag:1"`}}} {
			server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
			call := Call{Operation: operation(LaneManagement, "read-only", "none"), Header: header}
			call.Operation.HeaderParameters = declared
			if _, err := testExecutor(t, server).Do(context.Background(), call, nil); err != nil {
				t.Fatal(err)
			}
			var want []string
			if call.Operation.DeclaresHeader("If-Match") {
				want = []string{`"etag:1"`}
			}
			if got := rec.all()[0].header.Values("If-Match"); strings.Join(got, ",") != strings.Join(want, ",") {
				t.Fatalf("declared %q with caller %v: If-Match = %q, want %q", declared, header, got, want)
			}
		}
	}
	if !(Operation{HeaderParameters: []string{"if-match"}}).DeclaresHeader("If-Match") ||
		(Operation{HeaderParameters: []string{"Idempotency-Key"}}).DeclaresHeader("If-Match") {
		t.Fatal("DeclaresHeader does not compare header names case-insensitively")
	}
}

func TestExecutorDefaultHeadersYieldToCallerHeaders(t *testing.T) {
	server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
	executor := testExecutor(t, server)
	executor.DefaultHeaders = http.Header{"User-Agent": {"postgrip-test"}, "X-Default": {"default"}}
	call := Call{Operation: operation(LaneManagement, "read-only", "none"), Header: http.Header{"user-agent": {"caller-agent"}}}
	if _, err := executor.Do(context.Background(), call, nil); err != nil {
		t.Fatal(err)
	}
	header := rec.all()[0].header
	if got := header.Values("User-Agent"); len(got) != 1 || got[0] != "caller-agent" {
		t.Fatalf("User-Agent = %q", got)
	}
	if got := header.Get("X-Default"); got != "default" {
		t.Fatalf("X-Default = %q", got)
	}
}

func TestExecutorRequiredIdempotencyKey(t *testing.T) {
	for _, key := range []string{"", " key ", strings.Repeat("k", 129), "k\x7f"} {
		server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
		call := Call{Operation: operation(LaneManagement, "mutation", "required"), Header: http.Header{}}
		if key != "" {
			call.Header.Set("Idempotency-Key", key)
		}
		_, err := testExecutor(t, server).Do(context.Background(), call, nil)
		if err == nil || !strings.HasPrefix(err.Error(), "postgrip-test: idempotency key must contain") {
			t.Fatalf("key %q error = %v", key, err)
		}
		if len(rec.all()) != 0 {
			t.Fatalf("key %q reached the server", key)
		}
	}

	server, rec := recordingServer(t,
		status(http.StatusTooManyRequests, nil, `{}`),
		status(http.StatusBadGateway, nil, `{}`),
		status(http.StatusOK, nil, `{}`))
	executor := testExecutor(t, server)
	executor.Retry.Enabled = true
	call := Call{Operation: operation(LaneManagement, "mutation", "required"),
		Header: http.Header{"Idempotency-Key": {"mutation-1"}}, Body: map[string]any{"name": "value", "n": 1}}
	if _, err := executor.Do(context.Background(), call, nil); err != nil {
		t.Fatal(err)
	}
	requests := rec.all()
	if len(requests) != 3 {
		t.Fatalf("attempts = %d", len(requests))
	}
	for _, request := range requests {
		if request.header.Get("Idempotency-Key") != "mutation-1" || !bytes.Equal(request.body, requests[0].body) {
			t.Fatalf("attempt key=%q body=%s, first body=%s", request.header.Get("Idempotency-Key"), request.body, requests[0].body)
		}
	}
}

func TestExecutorSignsEncodedBodyAndNeverRetriesSignedRequests(t *testing.T) {
	server, rec := recordingServer(t, status(http.StatusServiceUnavailable, nil, `{}`))
	executor := testExecutor(t, server)
	executor.Retry.Enabled = true
	executor.Credentials.Delegated = func(context.Context) (string, error) { return "session", nil }
	var signed []byte
	executor.Sign = func(request *http.Request, body []byte) error {
		signed = append([]byte(nil), body...)
		request.Header.Set("X-Signature", "signature")
		return nil
	}
	op := operation(LaneAgent, "mutation", "none")
	op.Signing = "agent-task-v1"
	_, err := executor.Do(context.Background(), Call{Operation: op, Header: http.Header{"Idempotency-Key": {"key"}}, Body: map[string]string{"result": "ok"}}, nil)
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("error = %v", err)
	}
	requests := rec.all()
	if len(requests) != 1 {
		t.Fatalf("signed request attempts = %d", len(requests))
	}
	if !bytes.Equal(signed, requests[0].body) || requests[0].header.Get("X-Signature") != "signature" {
		t.Fatalf("signed %s, sent %s", signed, requests[0].body)
	}
}

func TestExecutorAcceptedStatusesReturnRawBody(t *testing.T) {
	server, _ := recordingServer(t, status(http.StatusGone, nil, `{"code":"SHUTDOWN"}`))
	executor := testExecutor(t, server)
	response, err := executor.Do(context.Background(), Call{Operation: operation(LaneManagement, "read-only", "none"), AcceptedStatuses: []int{http.StatusGone}}, nil)
	if err != nil || response.StatusCode != http.StatusGone || string(response.Body) != `{"code":"SHUTDOWN"}` {
		t.Fatalf("response = %#v, %v", response, err)
	}
	_, err = executor.Do(context.Background(), Call{Operation: operation(LaneManagement, "read-only", "none")}, nil)
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != "SHUTDOWN" {
		t.Fatalf("unaccepted 410 error = %v", err)
	}
}

func TestExecutorSuccessOnlyResponseBoundOverride(t *testing.T) {
	large := `"` + strings.Repeat("a", 64) + `"`
	server, _ := recordingServer(t, status(http.StatusOK, nil, large))
	executor := testExecutor(t, server)
	executor.MaxResponseBytes = 16
	executor.SuccessResponseBytes = map[string]int64{"testOperation": 128}
	var out string
	if _, err := executor.Do(context.Background(), Call{Operation: operation(LaneManagement, "read-only", "none")}, &out); err != nil || len(out) != 64 {
		t.Fatalf("override success = %q, %v", out, err)
	}
	other := operation(LaneManagement, "read-only", "none")
	other.ID = "otherOperation"
	if _, err := executor.Do(context.Background(), Call{Operation: other}, &out); err == nil || err.Error() != "postgrip-test: response is invalid or too large" {
		t.Fatalf("default bound error = %v", err)
	}

	errorServer, _ := recordingServer(t, status(http.StatusInternalServerError, nil, large))
	executor = testExecutor(t, errorServer)
	executor.MaxResponseBytes = 16
	executor.SuccessResponseBytes = map[string]int64{"testOperation": 128}
	if _, err := executor.Do(context.Background(), Call{Operation: operation(LaneManagement, "read-only", "none")}, nil); err == nil || err.Error() != "postgrip-test: response is invalid or too large" {
		t.Fatalf("override applied to an error body: %v", err)
	}
}

func TestExecutorRefusesProtocolAdapterOperations(t *testing.T) {
	server, rec := recordingServer(t, status(http.StatusOK, nil, `{}`))
	for _, op := range []Operation{{ID: "upload", StreamingRequest: true}, {ID: "socket", WebSocket: true}} {
		if _, err := testExecutor(t, server).Do(context.Background(), Call{Operation: op}, nil); err == nil {
			t.Fatalf("%s executed", op.ID)
		}
	}
	if len(rec.all()) != 0 {
		t.Fatal("protocol operation reached the server")
	}
}

func TestRetryEligibleNeverRetriesProtocolSignedStreamingOrWebSocket(t *testing.T) {
	base := operation(LaneManagement, "read-only", "none")
	if !RetryEligible(base, "") {
		t.Fatal("bounded read-only operation is not eligible")
	}
	mutation := operation(LaneManagement, "mutation", "required")
	if RetryEligible(mutation, "") || !RetryEligible(mutation, "key") {
		t.Fatal("mutation eligibility does not follow the idempotency key")
	}
	unbounded := base
	unbounded.Retry = "none"
	protocol := base
	protocol.Safety = "protocol"
	signed := base
	signed.Signing = "agent-task-v1"
	streaming := base
	streaming.StreamingRequest = true
	socket := base
	socket.WebSocket = true
	for _, op := range []Operation{unbounded, protocol, signed, streaming, socket} {
		if RetryEligible(op, "key") {
			t.Fatalf("%+v is retry eligible", op)
		}
	}
}

func TestRetryAfterOnlyControlsRateLimitAndServiceUnavailableBackoff(t *testing.T) {
	policy := RetryConfig{MaxDelay: 0, RetryAfterMax: 30 * time.Second}
	retryAfter := 30 * time.Second
	for _, status := range []int{http.StatusTooManyRequests, http.StatusServiceUnavailable} {
		if got := policy.delay(1, status, retryAfter, true); got != retryAfter {
			t.Fatalf("delay(%d) = %s, want %s", status, got, retryAfter)
		}
	}
	for _, status := range []int{http.StatusRequestTimeout, http.StatusBadGateway, http.StatusGatewayTimeout} {
		if got := policy.delay(1, status, retryAfter, true); got != 0 {
			t.Fatalf("delay(%d) = %s, want backoff", status, got)
		}
	}
	if got := (RetryConfig{RetryAfterMax: 5 * time.Second}).delay(1, http.StatusTooManyRequests, time.Minute, true); got != 5*time.Second {
		t.Fatalf("delay above ceiling = %s", got)
	}
}

func TestParseRetryAfter(t *testing.T) {
	maximum := 30 * time.Second
	for value, want := range map[string]time.Duration{
		"3": 3 * time.Second, "30": 30 * time.Second, "120": 30 * time.Second,
		"99999999999999999999999": 30 * time.Second, "0": 0,
	} {
		if got, ok := ParseRetryAfter(value, maximum); !ok || got != want {
			t.Fatalf("ParseRetryAfter(%q) = %s, %v; want %s", value, got, ok, want)
		}
	}
	for _, value := range []string{"", "soon", "-1"} {
		if got, ok := ParseRetryAfter(value, maximum); ok || got != 0 {
			t.Fatalf("ParseRetryAfter(%q) = %s, %v", value, got, ok)
		}
	}
	if got, ok := ParseRetryAfter(time.Now().Add(time.Hour).UTC().Format(http.TimeFormat), maximum); !ok || got != maximum {
		t.Fatalf("future date = %s, %v", got, ok)
	}
}
