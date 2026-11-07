package worker

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const snapshotRunBody = `{"snapshot":{"workerId":"11111111-1111-4111-8111-111111111111","snapshotId":"20261107T101500.000Z","size":1,"degraded":false,"skipped":[]},"receipt":{"requestId":"req","auditRecorded":true,"replayed":false}}`

func snapshotErrorServer(t *testing.T, attempts *atomic.Int32, status int, code string, header map[string]string) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		for name, value := range header {
			w.Header().Set(name, value)
		}
		w.WriteHeader(status)
		_, _ = io.WriteString(w, `{"code":"`+code+`","message":"refused","requestId":"req"}`)
	}))
	t.Cleanup(server.Close)
	return server
}

func TestSnapshotMutationsRequireIdempotencyKeyBeforeSending(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { calls.Add(1) }))
	defer server.Close()
	client := newTestClient(t, server, true)
	for _, key := range []string{"", " snapshot-1 ", strings.Repeat("k", 129)} {
		if _, err := client.TakeSnapshot(context.Background(), "worker", key); err == nil {
			t.Fatalf("TakeSnapshot(%q) error = nil", key)
		}
		if _, err := client.UpdateSnapshotSettings(context.Background(), "worker", UpdateWorkerSnapshotSettingsRequest{Enabled: false}, key); err == nil {
			t.Fatalf("UpdateSnapshotSettings(%q) error = nil", key)
		}
	}
	if calls.Load() != 0 {
		t.Fatalf("requests sent without a valid key: %d", calls.Load())
	}
}

func TestTakeSnapshotSendsKeyAndDecodesRun(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/workers/w/snapshots" || r.Header.Get("Idempotency-Key") != "snapshot-1" {
			t.Fatalf("request = %s %s key=%q", r.Method, r.URL.Path, r.Header.Get("Idempotency-Key"))
		}
		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, snapshotRunBody)
	}))
	defer server.Close()
	response, err := newTestClient(t, server, false).TakeSnapshot(context.Background(), "w", "snapshot-1")
	if err != nil || response.Snapshot.SnapshotId != "20261107T101500.000Z" || response.Snapshot.ObjectKey != nil || !response.Receipt.AuditRecorded {
		t.Fatalf("TakeSnapshot() = %#v, %v", response, err)
	}
}

func TestTakeSnapshotNeverRetriesUnkeptAnswers(t *testing.T) {
	for _, tc := range []struct {
		status int
		code   string
	}{
		{http.StatusGatewayTimeout, "SNAPSHOT_UNCONFIRMED"},
		{http.StatusBadGateway, "SNAPSHOT_FAILED"},
	} {
		var attempts atomic.Int32
		client := newTestClient(t, snapshotErrorServer(t, &attempts, tc.status, tc.code, nil), true)
		_, err := client.TakeSnapshot(context.Background(), "w", "snapshot-1")
		var apiErr *APIError
		if !errors.As(err, &apiErr) || apiErr.StatusCode != tc.status || apiErr.Code != tc.code {
			t.Fatalf("TakeSnapshot() error = %v", err)
		}
		if attempts.Load() != 1 {
			t.Fatalf("%s attempts = %d, want 1", tc.code, attempts.Load())
		}
		// The generated binding shares the plane's call policy.
		attempts.Store(0)
		if _, err := client.OpenAPI().CreateWorkerSnapshot(context.Background(), "w", OpenAPICreateWorkerSnapshotHeaders{IdempotencyKey: "snapshot-1"}); err == nil || attempts.Load() != 1 {
			t.Fatalf("OpenAPI CreateWorkerSnapshot error = %v; attempts = %d", err, attempts.Load())
		}
	}

	// Other snapshot operations keep the plane's bounded retry of a 504.
	var attempts atomic.Int32
	client := newTestClient(t, snapshotErrorServer(t, &attempts, http.StatusGatewayTimeout, "GATEWAY_TIMEOUT", nil), true)
	if _, err := client.SnapshotStatus(context.Background(), "w"); err == nil || attempts.Load() != retryMaxAttempts {
		t.Fatalf("SnapshotStatus() error = %v; attempts = %d", err, attempts.Load())
	}
}

func TestTakeSnapshotStillRetriesRateLimit(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Idempotency-Key") != "snapshot-1" {
			t.Fatalf("Idempotency-Key = %q", r.Header.Get("Idempotency-Key"))
		}
		if attempts.Add(1) == 1 {
			w.Header().Set("Retry-After", "0")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = io.WriteString(w, `{"code":"RATE_LIMITED","message":"slow down","requestId":"req"}`)
			return
		}
		w.WriteHeader(http.StatusCreated)
		_, _ = io.WriteString(w, snapshotRunBody)
	}))
	defer server.Close()
	if _, err := newTestClient(t, server, true).TakeSnapshot(context.Background(), "w", "snapshot-1"); err != nil || attempts.Load() != 2 {
		t.Fatalf("TakeSnapshot() error = %v; attempts = %d", err, attempts.Load())
	}
}

func TestTakeSnapshotInProgressExposesRetryAfterWithoutRetrying(t *testing.T) {
	var attempts atomic.Int32
	server := snapshotErrorServer(t, &attempts, http.StatusConflict, "SNAPSHOT_IN_PROGRESS", map[string]string{"Retry-After": "30"})
	_, err := newTestClient(t, server, true).TakeSnapshot(context.Background(), "w", "snapshot-1")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.Code != "SNAPSHOT_IN_PROGRESS" || apiErr.RetryAfter != 30*time.Second {
		t.Fatalf("TakeSnapshot() error = %#v", err)
	}
	if attempts.Load() != 1 {
		t.Fatalf("attempts = %d", attempts.Load())
	}
}

func TestTakeSnapshotOutlivesTheConfiguredTimeout(t *testing.T) {
	if snapshotRunLifetime <= 5*time.Minute {
		t.Fatalf("snapshot run lifetime %s does not exceed the server's 5-minute wait", snapshotRunLifetime)
	}
	if policy := operationCallPolicy[openAPICreateWorkerSnapshot]; policy.lifetime != snapshotRunLifetime {
		t.Fatalf("createWorkerSnapshot lifetime = %s", policy.lifetime)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(150 * time.Millisecond)
		if r.Method == http.MethodPost {
			w.WriteHeader(http.StatusCreated)
			_, _ = io.WriteString(w, snapshotRunBody)
			return
		}
		_, _ = io.WriteString(w, `{}`)
	}))
	defer server.Close()
	httpClient := server.Client()
	httpClient.Timeout = 50 * time.Millisecond
	client, err := New(Config{BaseURL: server.URL, Token: "pgt_test-token", InsecureDevelopment: true, HTTPClient: httpClient})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.TakeSnapshot(context.Background(), "w", "snapshot-1"); err != nil {
		t.Fatalf("TakeSnapshot() past the configured timeout error = %v", err)
	}
	if _, err := client.SnapshotStatus(context.Background(), "w"); err == nil {
		t.Fatal("SnapshotStatus() kept the configured timeout: want a timeout error")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if _, err := client.TakeSnapshot(ctx, "w", "snapshot-2"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("TakeSnapshot() with a shorter caller deadline error = %v", err)
	}
}

func TestUpdateSnapshotSettingsSigningKeyIsWriteOnly(t *testing.T) {
	var bodies []map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut || r.URL.Path != "/api/v1/workers/w/snapshot/settings" || r.Header.Get("Idempotency-Key") != "settings-1" {
			t.Fatalf("request = %s %s key=%q", r.Method, r.URL.Path, r.Header.Get("Idempotency-Key"))
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		bodies = append(bodies, body)
		// A hostile echo of the key must not survive decoding.
		_, _ = io.WriteString(w, `{"settings":{"workerId":"w","enabled":true,"volumesEnabled":false,"volumesHot":false,"hasSigningKey":true,"signingKey":"echoed-seed"},"receipt":{"requestId":"req","auditRecorded":true,"replayed":false}}`)
	}))
	defer server.Close()
	client := newTestClient(t, server, false)
	seed := "base64-seed"
	response, err := client.UpdateSnapshotSettings(context.Background(), "w", UpdateWorkerSnapshotSettingsRequest{Enabled: true, SigningKey: &seed}, "settings-1")
	if err != nil || !response.Settings.HasSigningKey {
		t.Fatalf("UpdateSnapshotSettings() = %#v, %v", response, err)
	}
	encoded, err := json.Marshal(response)
	if err != nil || strings.Contains(string(encoded), "signingKey") || strings.Contains(string(encoded), "echoed-seed") {
		t.Fatalf("response re-encodes the signing key: %s (%v)", encoded, err)
	}
	if _, err := client.UpdateSnapshotSettings(context.Background(), "w", UpdateWorkerSnapshotSettingsRequest{Enabled: false}, "settings-1"); err != nil {
		t.Fatal(err)
	}
	if bodies[0]["signingKey"] != seed {
		t.Fatalf("first body = %v", bodies[0])
	}
	if _, sent := bodies[1]["signingKey"]; sent || bodies[1]["enabled"] != false {
		t.Fatalf("omitted signing key was sent: %v", bodies[1])
	}
}

func TestSnapshotResponseTypesCarryNoSigningKey(t *testing.T) {
	seen := map[reflect.Type]bool{}
	var walk func(reflect.Type, string)
	walk = func(typ reflect.Type, path string) {
		for typ.Kind() == reflect.Pointer || typ.Kind() == reflect.Slice || typ.Kind() == reflect.Map {
			typ = typ.Elem()
		}
		if typ.Kind() != reflect.Struct || seen[typ] {
			return
		}
		seen[typ] = true
		for i := 0; i < typ.NumField(); i++ {
			field := typ.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			if strings.EqualFold(name, "signingKey") || field.Name == "SigningKey" {
				t.Errorf("%s.%s carries the write-only signing key", path, field.Name)
			}
			walk(field.Type, path+"."+field.Name)
		}
	}
	for _, value := range []any{
		WorkerSnapshotStatus{}, WorkerSnapshotList{}, CreateWorkerSnapshotResponse{},
		WorkerSnapshotSettings{}, UpdateWorkerSnapshotSettingsResponse{},
	} {
		walk(reflect.TypeOf(value), reflect.TypeOf(value).Name())
	}
}
