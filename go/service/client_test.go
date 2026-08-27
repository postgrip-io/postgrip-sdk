package service

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func newTestClient(t *testing.T, handler http.Handler, configure func(*Config)) *Client {
	t.Helper()
	server := httptest.NewTLSServer(handler)
	t.Cleanup(server.Close)
	config := Config{BaseURL: server.URL, Token: "pgt_test-token", HTTPClient: server.Client()}
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
		{BaseURL: "http://example.test", Token: "pgt_token"},
		{BaseURL: "https://example.test?query=yes", Token: "pgt_token"},
		{BaseURL: "https://example.test?", Token: "pgt_token"},
		{BaseURL: "https://example.test#", Token: "pgt_token"},
		{BaseURL: "https://example.test", Token: "   "},
		{BaseURL: "https://example.test", Token: "pgt_token", RetryMaxAttempts: 4},
		{BaseURL: "https://example.test", Token: "pgt_token", RetryMaxDelay: 3 * time.Second},
		{BaseURL: "https://example.test", Token: "pgt_token", RetryAfterMaxDelay: 31 * time.Second},
	} {
		if _, err := New(config); err == nil {
			t.Fatalf("New(%+v) succeeded", config)
		}
	}
}

func TestNewAcceptsOpaqueManagementToken(t *testing.T) {
	if _, err := New(Config{BaseURL: "https://example.test", Token: "opaque-token"}); err != nil {
		t.Fatalf("New rejected an opaque token: %v", err)
	}
}

func TestNewFromEnvUsesServiceConfiguration(t *testing.T) {
	t.Setenv("POSTGRIP_URL", "https://common.example.test")
	t.Setenv("POSTGRIP_SERVICE_URL", "https://services.example.test")
	t.Setenv("POSTGRIP_TOKEN", "pgt_environment-token")
	client, err := NewFromEnv(Config{})
	if err != nil {
		t.Fatal(err)
	}
	if client.connection.baseURL.String() != "https://services.example.test" || client.connection.token != "pgt_environment-token" {
		t.Fatalf("environment client = %+v", client.connection)
	}
}

func TestListAndResolveUseGeneratedRoutesAndBearerToken(t *testing.T) {
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if got := r.Header.Get("Authorization"); got != "Bearer pgt_test-token" {
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

func TestAdministrationFacadeSendsCatalogFence(t *testing.T) {
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/services/targets" {
			t.Fatalf("request = %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Idempotency-Key") != "attach-1" || r.Header.Get("If-Match") != `"catalog:4"` {
			t.Fatalf("headers = %#v", r.Header)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"target":{},"operation":{},"receipt":{"requestId":"request-id","auditRecorded":true,"replayed":false}}`))
	}), nil)

	host, port, databaseName := "db.internal", int64(5432), "app"
	_, err := client.TargetServices().Attach(context.Background(), OpenAPIAttachTargetServiceRequestBody{
		WorkerId: "11111111-1111-4111-8111-111111111111", Name: "db", Slug: "db",
		Host: &host, Port: &port, DatabaseName: &databaseName, Metadata: OpenAPIServiceTargetMetadataRequest{},
	}, WriteOptions{IdempotencyKey: "attach-1", IfMatch: `"catalog:4"`})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.ServiceConfigurationOperations().Retry(context.Background(), "operation-id", WriteOptions{
		IdempotencyKey: "retry-1", IfMatch: "bad\r\netag",
	}); err == nil {
		t.Fatal("malformed ETag succeeded")
	}
}

func TestBulkVariableApplyUsesPerEnvironmentFencesWithoutIfMatch(t *testing.T) {
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/services/project/project-id/variables/apply" {
			t.Fatalf("request = %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Idempotency-Key") != "apply-1" {
			t.Fatalf("Idempotency-Key = %q", r.Header.Get("Idempotency-Key"))
		}
		if got := r.Header.Get("If-Match"); got != "" {
			t.Fatalf("If-Match = %q, want empty", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results":[],"receipt":{"requestId":"request-id","auditRecorded":true,"replayed":false}}`))
	}), nil)

	_, err := client.ServiceVariables().Apply(context.Background(), "project-id", OpenAPIApplyServiceVariablesRequestBody{
		Changes: []OpenAPIServiceVariableApplyChange{{
			EnvironmentId:             "environment-id",
			Name:                      "DATABASE_URL",
			IsSecret:                  true,
			Value:                     func() *string { value := "postgres://example"; return &value }(),
			ExpectedCollectionVersion: 7,
		}},
	}, MutationOptions{IdempotencyKey: "apply-1"})
	if err != nil {
		t.Fatal(err)
	}
}

func TestAdministrationFacadeCoversAllAdministrationOperations(t *testing.T) {
	types := []reflect.Type{
		reflect.TypeOf(TargetServicesClient{}),
		reflect.TypeOf(ProjectsClient{}),
		reflect.TypeOf(ServiceEnvironmentsClient{}),
		reflect.TypeOf(ManagedVolumesClient{}),
		reflect.TypeOf(ServiceDomainsClient{}),
		reflect.TypeOf(ServiceVariablesClient{}),
		reflect.TypeOf(ServiceRepositoriesClient{}),
		reflect.TypeOf(ServicePromotionsClient{}),
		reflect.TypeOf(ServiceRetentionClient{}),
		reflect.TypeOf(ServiceConfigurationOperationsClient{}),
		reflect.TypeOf(DeclarativeConfigurationClient{}),
	}
	operationCount := 0
	for _, facadeType := range types {
		operationCount += facadeType.NumMethod()
	}
	if operationCount != 68 {
		t.Fatalf("administration facade operations = %d, want 68", operationCount)
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

func TestRetriesAreDisabledByDefault(t *testing.T) {
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"code":"WORKER_UNAVAILABLE","message":"try later","requestId":"request-id"}`))
	}), nil)

	_, err := client.Resolve(context.Background(), "api")
	if err == nil || calls.Load() != 1 {
		t.Fatalf("err = %v, calls = %d", err, calls.Load())
	}
}

func TestRetryConfigurationCapsAttemptsAndRetryAfter(t *testing.T) {
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.Header().Set("Retry-After", "30")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"code":"WORKER_UNAVAILABLE","message":"try later","requestId":"request-id"}`))
	}), func(config *Config) {
		config.EnableRetries = true
		config.RetryMaxAttempts = 2
		config.RetryAfterMaxDelay = time.Millisecond
	})

	_, err := client.Resolve(context.Background(), "api")
	apiErr, ok := err.(*APIError)
	if !ok || calls.Load() != 2 || apiErr.RetryAfter != time.Millisecond {
		t.Fatalf("err = %#v, calls = %d", err, calls.Load())
	}
}

func TestRetryAfterPreservesZeroAndCapsOversizedValues(t *testing.T) {
	policy := serviceRetryLimits{maxDelay: 2 * time.Second, retryAfterMax: 30 * time.Second}
	response := &http.Response{StatusCode: http.StatusServiceUnavailable, Header: http.Header{"Retry-After": []string{"0"}}}
	apiErr, retryAfterSet := decodeAPIError(response, nil, policy.retryAfterMax)
	retryAfter, retryAfterSet := retryAfterForStatus(response.StatusCode, apiErr.RetryAfter, retryAfterSet)
	if !retryAfterSet || retryAfter != 0 {
		t.Fatalf("Retry-After zero = %s, present = %v", retryAfter, retryAfterSet)
	}
	if delay := retryDelay(1, retryAfter, retryAfterSet, policy); delay != 0 {
		t.Fatalf("retry delay = %s, want zero", delay)
	}

	retryAfter, retryAfterSet = parseRetryAfter(strings.Repeat("9", 100), policy.retryAfterMax)
	if !retryAfterSet || retryAfter != policy.retryAfterMax {
		t.Fatalf("oversized Retry-After = %s, present = %v", retryAfter, retryAfterSet)
	}
}

func TestCancellationInterruptsRetryBackoff(t *testing.T) {
	called := make(chan struct{}, 1)
	var calls atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		called <- struct{}{}
		w.Header().Set("Retry-After", "30")
		w.WriteHeader(http.StatusServiceUnavailable)
	}), func(config *Config) { config.EnableRetries = true })
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := client.Resolve(ctx, "api")
		done <- err
	}()
	<-called
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) || calls.Load() != 1 {
			t.Fatalf("err = %v, calls = %d", err, calls.Load())
		}
	case <-time.After(time.Second):
		t.Fatal("retry backoff ignored cancellation")
	}
}

func TestResponseBodyLimit(t *testing.T) {
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(strings.Repeat("x", maxResponseBytes+1)))
	}), nil)
	_, err := client.Resolve(context.Background(), "api")
	if err == nil || !strings.Contains(err.Error(), "too large") {
		t.Fatalf("err = %v", err)
	}
}

func TestCrossOriginRedirectDoesNotForwardBearer(t *testing.T) {
	var destinationCalls atomic.Int32
	destination := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		destinationCalls.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer destination.Close()
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Location", destination.URL+"/api/v1/services")
		w.WriteHeader(http.StatusTemporaryRedirect)
	}), nil)

	_, err := client.Resolve(context.Background(), "api")
	apiErr, ok := err.(*APIError)
	if !ok || apiErr.StatusCode != http.StatusTemporaryRedirect || destinationCalls.Load() != 0 {
		t.Fatalf("err = %#v, destination calls = %d", err, destinationCalls.Load())
	}
}

func TestEveryServiceFacadeMapsToCanonicalOperation(t *testing.T) {
	expected := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/api/v1/services"},
		{http.MethodGet, "/api/v1/services/resolve"},
		{http.MethodGet, "/api/v1/services/project/service-id"},
		{http.MethodGet, "/api/v1/services/project/service-id/status"},
		{http.MethodGet, "/api/v1/services/project/service-id/environments"},
		{http.MethodGet, "/api/v1/services/project/service-id/environments/resolve"},
		{http.MethodGet, "/api/v1/services/project/service-id/deployments"},
		{http.MethodGet, "/api/v1/services/project/service-id/deployments/deployment-id"},
		{http.MethodGet, "/api/v1/services/project/service-id/logs"},
		{http.MethodPost, "/api/v1/services/project/service-id/check"},
		{http.MethodGet, "/api/v1/services/project/service-id/deploy/preview"},
		{http.MethodPost, "/api/v1/services/project/service-id/deploy"},
		{http.MethodPost, "/api/v1/services/project/service-id/redeploy"},
		{http.MethodPost, "/api/v1/services/project/service-id/deployments/deployment-id/cancel"},
		{http.MethodPost, "/api/v1/services/project/service-id/deployments/deployment-id/rollback"},
		{http.MethodPost, "/api/v1/services/project/service-id/environments/environment-id/start"},
		{http.MethodPost, "/api/v1/services/project/service-id/environments/environment-id/stop"},
		{http.MethodPost, "/api/v1/services/project/service-id/environments/environment-id/restart"},
	}
	var index atomic.Int32
	client := newTestClient(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := int(index.Add(1) - 1)
		if current >= len(expected) || r.Method != expected[current].method || r.URL.Path != expected[current].path {
			t.Fatalf("request %d = %s %s", current, r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}), nil)
	ref := Reference{Source: OpenAPIServiceSourceProject, ID: "service-id"}
	invocations := []func() error{
		func() error { _, err := client.List(context.Background(), OpenAPIListServicesQuery{}); return err },
		func() error { _, err := client.Resolve(context.Background(), "api"); return err },
		func() error { _, err := client.Get(context.Background(), ref); return err },
		func() error {
			_, err := client.Status(context.Background(), ref, OpenAPIGetServiceStatusQuery{})
			return err
		},
		func() error {
			_, err := client.Environments(context.Background(), ref, OpenAPIListServiceEnvironmentsQuery{})
			return err
		},
		func() error {
			_, err := client.ResolveEnvironment(context.Background(), "service-id", "production")
			return err
		},
		func() error {
			_, err := client.Deployments(context.Background(), ref, OpenAPIListServiceDeploymentsQuery{})
			return err
		},
		func() error {
			_, err := client.Deployment(context.Background(), "service-id", "deployment-id")
			return err
		},
		func() error {
			_, err := client.Logs(context.Background(), ref, OpenAPIListServiceLogsQuery{})
			return err
		},
		func() error { _, err := client.Check(context.Background(), ref, nil, "key"); return err },
		func() error {
			_, err := client.PreviewDeploy(context.Background(), "service-id", OpenAPIPreviewServiceDeployQuery{})
			return err
		},
		func() error {
			_, err := client.Deploy(context.Background(), "service-id", DeployServiceRequest{ExpectedCommitSha: "sha"}, "key")
			return err
		},
		func() error {
			_, err := client.Redeploy(context.Background(), "service-id", RedeployServiceRequest{}, "key")
			return err
		},
		func() error {
			_, err := client.Cancel(context.Background(), "service-id", "deployment-id", "key")
			return err
		},
		func() error {
			_, err := client.Rollback(context.Background(), "service-id", "deployment-id", "key")
			return err
		},
		func() error {
			_, err := client.Start(context.Background(), "service-id", "environment-id", "deployment-id", "key")
			return err
		},
		func() error {
			_, err := client.Stop(context.Background(), "service-id", "environment-id", "deployment-id", "key")
			return err
		},
		func() error {
			_, err := client.Restart(context.Background(), "service-id", "environment-id", "deployment-id", "key")
			return err
		},
	}
	for operation, invoke := range invocations {
		if err := invoke(); err != nil {
			t.Fatalf("operation %d: %v", operation, err)
		}
	}
	if int(index.Load()) != len(expected) {
		t.Fatalf("calls = %d, want %d", index.Load(), len(expected))
	}
}
