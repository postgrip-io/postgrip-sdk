package serviceclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func newTestClient(t *testing.T, handler http.Handler, configure func(*Config)) *Client {
	t.Helper()
	server := httptest.NewTLSServer(handler)
	t.Cleanup(server.Close)
	config := Config{BaseURL: server.URL, Token: "pgwm_test-token", HTTPClient: server.Client()}
	if configure != nil {
		configure(&config)
	}
	client, err := New(config)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestNewRejectsUnsafeConfiguration(t *testing.T) {
	for _, config := range []Config{
		{BaseURL: "http://example.test", Token: "pgwm_token"},
		{BaseURL: "https://example.test?query=yes", Token: "pgwm_token"},
		{BaseURL: "https://example.test", Token: "not-a-token"},
	} {
		if _, err := New(config); err == nil {
			t.Fatalf("New(%+v) succeeded", config)
		}
	}
}

func TestListAndResolveUseGeneratedRoutesAndBearerToken(t *testing.T) {
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if got := r.Header.Get("Authorization"); got != "Bearer pgwm_test-token" {
			t.Errorf("Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/v1/services":
			if r.URL.Query().Get("kind") != "backend" || r.URL.Query().Get("limit") != "10" {
				t.Errorf("query = %q", r.URL.RawQuery)
			}
			_, _ = w.Write([]byte(`{"items":[],"nextCursor":""}`))
		case "/api/v1/services/resolve":
			if r.URL.Query().Get("value") != "api" {
				t.Errorf("value = %q", r.URL.Query().Get("value"))
			}
			_, _ = w.Write([]byte(`{"ref":"project:11111111-1111-4111-8111-111111111111","id":"11111111-1111-4111-8111-111111111111","source":"project","facets":[],"name":"api","slug":"api","kind":"backend","mode":"deployed","status":"ready","workers":[],"environmentCount":1,"capabilities":[],"createdAt":"2026-08-24T00:00:00Z","updatedAt":"2026-08-24T00:00:00Z"}`))
		default:
			http.NotFound(w, r)
		}
	}), nil)

	kind := OpenAPIServiceKindBackend
	limit := int64(10)
	if _, err := client.List(context.Background(), OpenAPIListServicesQuery{Kind: &kind, Limit: &limit}); err != nil {
		t.Fatal(err)
	}
	service, err := client.Resolve(context.Background(), "api")
	if err != nil {
		t.Fatal(err)
	}
	if service.Name != "api" || calls.Load() != 2 {
		t.Fatalf("service = %+v, calls = %d", service, calls.Load())
	}
}

func TestDeploySendsBodyAndIdempotencyKey(t *testing.T) {
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/services/project/project-id/deploy" {
			t.Fatalf("request = %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("Idempotency-Key"); got != "deploy-1" {
			t.Errorf("Idempotency-Key = %q", got)
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["expectedCommitSha"] != "abc123" {
			t.Errorf("body = %#v", body)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"queued","serviceRef":"project:project-id","environmentId":"env-id","deploymentId":"deployment-id","deployment":{"id":"deployment-id","projectId":"project-id","environmentId":"env-id","commitSha":"abc123","branch":"main","triggerKind":"manual","status":"queued","isCurrent":false,"createdAt":"2026-08-24T00:00:00Z","updatedAt":"2026-08-24T00:00:00Z"},"receipt":{"requestId":"request-id","auditRecorded":true,"replayed":false}}`))
	}), nil)

	response, err := client.Deploy(context.Background(), "project-id", DeployServiceRequest{ExpectedCommitSha: "abc123"}, "deploy-1")
	if err != nil {
		t.Fatal(err)
	}
	if response.DeploymentId != "deployment-id" {
		t.Fatalf("response = %+v", response)
	}
	if _, err := client.Deploy(context.Background(), "project-id", DeployServiceRequest{}, "contains space"); err == nil {
		t.Fatal("invalid idempotency key succeeded")
	}
}

func TestServicePagerUsesOpaqueCursor(t *testing.T) {
	var page atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if page.Add(1) == 1 {
			if r.URL.Query().Get("cursor") != "" {
				t.Errorf("first cursor = %q", r.URL.Query().Get("cursor"))
			}
			_, _ = w.Write([]byte(`{"items":[],"nextCursor":"next"}`))
			return
		}
		if r.URL.Query().Get("cursor") != "next" {
			t.Errorf("second cursor = %q", r.URL.Query().Get("cursor"))
		}
		_, _ = w.Write([]byte(`{"items":[],"nextCursor":""}`))
	}), nil)

	pager := client.Services(OpenAPIListServicesQuery{})
	if !pager.Next(context.Background()) || pager.Page().NextCursor != "next" {
		t.Fatalf("first page failed: %v", pager.Err())
	}
	if !pager.Next(context.Background()) || pager.Page().NextCursor != "" {
		t.Fatalf("second page failed: %v", pager.Err())
	}
	if pager.Next(context.Background()) || page.Load() != 2 {
		t.Fatalf("pager did not stop, calls = %d", page.Load())
	}
}

func TestFollowLogsUsesServerCursorAndCancelsDelay(t *testing.T) {
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		call := calls.Add(1)
		if r.URL.Query().Get("follow") != "true" {
			t.Errorf("follow = %q", r.URL.Query().Get("follow"))
		}
		if call > 1 && r.URL.Query().Get("cursor") != "cursor-1" {
			t.Errorf("cursor = %q", r.URL.Query().Get("cursor"))
		}
		w.Header().Set("Content-Type", "application/json")
		if call == 1 {
			_, _ = w.Write([]byte(`{"items":[{"kind":"runtime","message":"ready"}],"nextCursor":"cursor-1","pollAfterMs":1}`))
			return
		}
		_, _ = w.Write([]byte(`{"items":[],"nextCursor":"cursor-1","pollAfterMs":60000}`))
	}), nil)

	iterator := client.FollowLogs(Reference{Source: OpenAPIServiceSourceProject, ID: "project-id"}, OpenAPIListServiceLogsQuery{})
	ctx, cancel := context.WithCancel(context.Background())
	if !iterator.Next(ctx) || iterator.Entry().Message != "ready" {
		t.Fatalf("first entry failed: %v", iterator.Err())
	}
	done := make(chan bool, 1)
	go func() { done <- iterator.Next(ctx) }()
	for calls.Load() < 2 {
		time.Sleep(time.Millisecond)
	}
	cancel()
	select {
	case next := <-done:
		if next || iterator.Err() != context.Canceled {
			t.Fatalf("next = %v, err = %v", next, iterator.Err())
		}
	case <-time.After(time.Second):
		t.Fatal("cancellation did not interrupt log follow")
	}
}

func TestAPIErrorDoesNotExposeResponseBody(t *testing.T) {
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-Request-ID", "request-header")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte("secret upstream body"))
	}), nil)

	_, err := client.Resolve(context.Background(), "api")
	apiErr, ok := err.(*APIError)
	if !ok {
		t.Fatalf("error = %T %v", err, err)
	}
	if apiErr.Code != "HTTP_ERROR" || apiErr.RequestID != "request-header" || strings.Contains(apiErr.Error(), "secret") {
		t.Fatalf("API error = %+v", apiErr)
	}
}
