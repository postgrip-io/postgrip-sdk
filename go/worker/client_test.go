package worker

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func newTestClient(t *testing.T, server *httptest.Server, retries bool) *Client {
	t.Helper()
	client, err := New(Config{BaseURL: server.URL, Token: "pgt_test-token", InsecureDevelopment: true, EnableRetries: retries, FollowInterval: time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestNewFromEnvUsesWorkerConfiguration(t *testing.T) {
	t.Setenv("POSTGRIP_URL", "https://common.example.test")
	t.Setenv("POSTGRIP_WORKER_URL", "https://workers.example.test")
	t.Setenv("POSTGRIP_TOKEN", "pgt_environment-token")
	client, err := NewFromEnv(Config{})
	if err != nil {
		t.Fatal(err)
	}
	if client.connection.baseURL.String() != "https://workers.example.test" || client.connection.token != "pgt_environment-token" {
		t.Fatalf("environment client = %+v", client.connection)
	}
}

func TestListInjectsBearerAndEncodesQuery(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer pgt_test-token" {
			t.Fatalf("Authorization = %q", got)
		}
		if got := r.URL.Query().Get("pageSize"); got != "25" {
			t.Fatalf("pageSize = %q", got)
		}
		_, _ = w.Write([]byte(`{"items":[]}`))
	}))
	defer server.Close()

	pageSize := int64(25)
	page, err := newTestClient(t, server, false).List(context.Background(), ListWorkersOptions{PageSize: &pageSize})
	if err != nil || len(page.Items) != 0 {
		t.Fatalf("List() = %#v, %v", page, err)
	}
}

func TestListPreservesConfiguredBasePath(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got, want := r.URL.Path, "/postgrip/api/v1/workers"; got != want {
			t.Fatalf("path = %q, want %q", got, want)
		}
		_, _ = w.Write([]byte(`{"items":[]}`))
	}))
	defer server.Close()

	client, err := New(Config{
		BaseURL:             server.URL + "/postgrip/",
		Token:               "pgt_test-token",
		InsecureDevelopment: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.List(context.Background(), ListWorkersOptions{}); err != nil {
		t.Fatal(err)
	}
}

func TestOperationalLogQueryEncodesSinceAsRFC3339(t *testing.T) {
	since := time.Date(2026, time.August, 24, 12, 34, 56, 789, time.FixedZone("offset", -7*60*60))
	query := OpenAPIListWorkerOperationalLogsQuery{Since: &since}
	if got, want := query.values().Get("since"), since.Format(time.RFC3339Nano); got != want {
		t.Fatalf("since = %q, want %q", got, want)
	}
}

func TestMutationSendsIdempotencyKeyAndRetriesOnlyWhenEnabled(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Idempotency-Key"); got != "upgrade-1" {
			t.Fatalf("Idempotency-Key = %q", got)
		}
		if attempts.Add(1) < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"code":"BUSY","message":"busy","requestId":"req"}`))
			return
		}
		_, _ = w.Write([]byte(`{"status":"queued","worker":{"id":"w","name":"worker","status":"active","trustState":"trusted","createdAt":"2026-01-01T00:00:00Z","updatedAt":"2026-01-01T00:00:00Z","capabilities":[],"previewSubdomainEnabled":false,"autoShutdownOnRemoval":false},"lifecycleDirective":"upgrade","expectedVersion":2,"workerImage":"image","expectedSignerVersion":3,"signerImage":"signer","receipt":{"requestId":"req","auditRecorded":true,"replayed":false}}`))
	}))
	defer server.Close()

	response, err := newTestClient(t, server, true).Upgrade(context.Background(), "w", "upgrade-1")
	if err != nil || response.ExpectedVersion != 2 || response.ExpectedSignerVersion != 3 || response.SignerImage != "signer" || attempts.Load() != 3 {
		t.Fatalf("Upgrade() = %#v, %v; attempts=%d", response, err, attempts.Load())
	}
}

func TestTypedErrorAndRetriesDisabledByDefault(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		attempts.Add(1)
		w.Header().Set("Retry-After", "3")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"code":"WORKER_UNAVAILABLE","message":"try later","requestId":"req-1","details":{"safe":true}}`))
	}))
	defer server.Close()

	_, err := newTestClient(t, server, false).Get(context.Background(), "worker")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != "WORKER_UNAVAILABLE" || apiErr.RequestID != "req-1" || apiErr.RetryAfter != 3*time.Second {
		t.Fatalf("Get() error = %#v", err)
	}
	if attempts.Load() != 1 {
		t.Fatalf("attempts = %d", attempts.Load())
	}
}

func TestRetryAfterOnlyControlsRateLimitAndServiceUnavailableBackoff(t *testing.T) {
	retryAfter := 30 * time.Second
	for _, status := range []int{http.StatusTooManyRequests, http.StatusServiceUnavailable} {
		if got := retryAfterForStatus(status, retryAfter); got != retryAfter {
			t.Fatalf("retryAfterForStatus(%d) = %s, want %s", status, got, retryAfter)
		}
	}
	for _, status := range []int{http.StatusRequestTimeout, http.StatusBadGateway, http.StatusGatewayTimeout} {
		if got := retryAfterForStatus(status, retryAfter); got != 0 {
			t.Fatalf("retryAfterForStatus(%d) = %s, want 0", status, got)
		}
	}
}

func TestMalformedErrorUsesSafeCodeAndRequestHeader(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-Request-ID", "req-fallback")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`"not-an-object"`))
	}))
	defer server.Close()

	_, err := newTestClient(t, server, false).Get(context.Background(), "worker")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != "HTTP_ERROR" || apiErr.RequestID != "req-fallback" {
		t.Fatalf("Get() error = %#v", err)
	}
}

func TestMutationRejectsWhitespaceInIdempotencyKey(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls.Add(1) }))
	defer server.Close()

	_, err := newTestClient(t, server, false).Upgrade(context.Background(), "worker", " upgrade-1 ")
	if err == nil || calls.Load() != 0 {
		t.Fatalf("Upgrade() error = %v; calls=%d", err, calls.Load())
	}
}

func TestCrossOriginRedirectDoesNotForwardBearer(t *testing.T) {
	var targetCalls atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { targetCalls.Add(1) }))
	defer target.Close()
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Redirect(w, &http.Request{}, target.URL, http.StatusFound)
	}))
	defer source.Close()

	_, err := newTestClient(t, source, false).Get(context.Background(), "worker")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusFound {
		t.Fatalf("Get() error = %#v", err)
	}
	if targetCalls.Load() != 0 {
		t.Fatalf("redirect target received %d requests", targetCalls.Load())
	}
}

func TestOperationalLogIteratorCancelsEmptyPolling(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":"cursor"}`)
	}))
	defer server.Close()
	client := newTestClient(t, server, false)
	iterator := client.FollowOperationalLogs("worker", OpenAPIListWorkerOperationalLogsQuery{})
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
	defer cancel()
	if iterator.Next(ctx) || !errors.Is(iterator.Err(), context.DeadlineExceeded) {
		t.Fatalf("Next() = true or Err() = %v", iterator.Err())
	}
}

func TestOperationalLogIteratorDropsOverlappingIDsWithConstantState(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if requests.Add(1) == 1 {
			_, _ = fmt.Fprint(w, `{"items":[{"id":1}],"nextCursor":"first"}`)
			return
		}
		_, _ = fmt.Fprint(w, `{"items":[{"id":1},{"id":2}],"nextCursor":"second"}`)
	}))
	defer server.Close()
	iterator := newTestClient(t, server, false).FollowOperationalLogs("worker", OpenAPIListWorkerOperationalLogsQuery{})
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if !iterator.Next(ctx) || iterator.Entry().Id != 1 {
		t.Fatalf("first Next() = %v, entry=%#v, err=%v", iterator.Err() == nil, iterator.Entry(), iterator.Err())
	}
	if !iterator.Next(ctx) || iterator.Entry().Id != 2 {
		t.Fatalf("second Next() = %v, entry=%#v, err=%v", iterator.Err() == nil, iterator.Entry(), iterator.Err())
	}
}

func TestOperationalLogIteratorStopsBeforeBufferedEntryAfterCancel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = fmt.Fprint(w, `{"items":[{"id":1},{"id":2}],"nextCursor":"cursor"}`)
	}))
	defer server.Close()
	iterator := newTestClient(t, server, false).FollowOperationalLogs("worker", OpenAPIListWorkerOperationalLogsQuery{})
	ctx, cancel := context.WithCancel(context.Background())
	if !iterator.Next(ctx) || iterator.Entry().Id != 1 {
		t.Fatalf("first Next() failed: entry=%#v err=%v", iterator.Entry(), iterator.Err())
	}
	cancel()
	if iterator.Next(ctx) || !errors.Is(iterator.Err(), context.Canceled) {
		t.Fatalf("buffered Next() = true or Err() = %v", iterator.Err())
	}
}

func TestNewRequiresHTTPSAndWorkerToken(t *testing.T) {
	if _, err := New(Config{BaseURL: "http://example.com", Token: "pgt_token"}); err == nil {
		t.Fatal("New accepted HTTP without insecure development")
	}
	if _, err := New(Config{BaseURL: "https://example.com", Token: "pga_token"}); err == nil {
		t.Fatal("New accepted a non-worker token")
	}
}
