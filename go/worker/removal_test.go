package worker

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

const workerRemovalImpactBody = `{"workerId":"9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11","etag":"\"worker-removal-5f2c\"","serviceCount":2,"managedVolumeCount":1,` +
	`"unreachableVolumes":[{"volumeRef":"5d1e2f3a-4b5c-4d6e-8f70-819a2b3c4d5e","projectId":"3c8e2a1f-5b7d-4e9c-a2f0-6d1b8e4c7a93","name":"data","state":"retained"}],` +
	`"projects":[{"id":"3c8e2a1f-5b7d-4e9c-a2f0-6d1b8e4c7a93","name":"storefront","exclusive":true,"usesAsDefault":false},` +
	`{"id":"7a4d9e2c-1f3b-4c8a-b6e0-2d5f9a1c3e78","name":"billing","exclusive":false,"usesAsDefault":true}]}`

const removeWorkerBody = `{"workerId":"9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11","shutdownRequested":true,"deletedServiceCount":2,"deletedProjectCount":1,` +
	`"keptProjectCount":1,"unassignedEnvironmentCount":1,"clearedProjectDefaultCount":1,"workerCleanup":{"attempted":4,"failed":1,"skipped":0},` +
	`"receipt":{"requestId":"req_01","auditRecorded":true,"replayed":false}}`

func TestRemovalImpactReadsTheWorkerImpact(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/api/v1/workers/worker-1/removal-impact" || r.URL.RawQuery != "" {
			t.Fatalf("request = %s %s?%s", r.Method, r.URL.Path, r.URL.RawQuery)
		}
		if r.Header.Get("Authorization") != "Bearer pgt_test-token" || r.Header.Get("Idempotency-Key") != "" || r.Header.Get("If-Match") != "" {
			t.Fatalf("authorization=%q idempotency=%q if-match=%q", r.Header.Get("Authorization"), r.Header.Get("Idempotency-Key"), r.Header.Get("If-Match"))
		}
		w.Header().Set("ETag", `"worker-removal-5f2c"`)
		_, _ = io.WriteString(w, workerRemovalImpactBody)
	}))
	defer server.Close()
	impact, err := newTestClient(t, server, false).RemovalImpact(context.Background(), "worker-1")
	if err != nil {
		t.Fatal(err)
	}
	if impact.Etag != `"worker-removal-5f2c"` || impact.ServiceCount != 2 || impact.ManagedVolumeCount != 1 ||
		len(impact.UnreachableVolumes) != 1 || impact.UnreachableVolumes[0].State != "retained" || len(impact.Projects) != 2 ||
		!impact.Projects[0].Exclusive || impact.Projects[0].UsesAsDefault || impact.Projects[1].Exclusive || !impact.Projects[1].UsesAsDefault {
		t.Fatalf("RemovalImpact() = %#v", impact)
	}
}

func TestRemoveSendsBothFencesAndNoBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if r.Method != http.MethodDelete || r.URL.Path != "/api/v1/workers/worker-1" || len(body) != 0 || r.Header.Get("Content-Type") != "" {
			t.Fatalf("request = %s %s body=%q content-type=%q", r.Method, r.URL.Path, body, r.Header.Get("Content-Type"))
		}
		if r.Header.Get("Idempotency-Key") != "remove-1" || r.Header.Get("If-Match") != `"worker-removal-5f2c"` {
			t.Fatalf("idempotency=%q if-match=%q", r.Header.Get("Idempotency-Key"), r.Header.Get("If-Match"))
		}
		_, _ = io.WriteString(w, removeWorkerBody)
	}))
	defer server.Close()
	removed, err := newTestClient(t, server, false).Remove(context.Background(), "worker-1",
		RemoveOptions{IdempotencyKey: "remove-1", IfMatch: `"worker-removal-5f2c"`})
	if err != nil {
		t.Fatal(err)
	}
	if !removed.ShutdownRequested || removed.DeletedServiceCount != 2 || removed.DeletedProjectCount != 1 || removed.KeptProjectCount != 1 ||
		removed.UnassignedEnvironmentCount != 1 || removed.ClearedProjectDefaultCount != 1 || removed.WorkerCleanup.Failed != 1 ||
		removed.Receipt.RequestId != "req_01" {
		t.Fatalf("Remove() = %#v", removed)
	}
}

func TestRemoveValidatesItsFencesBeforeAnyRequest(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { requests.Add(1) }))
	defer server.Close()
	client := newTestClient(t, server, true)
	for _, options := range []RemoveOptions{
		{IfMatch: `"impact"`},
		{IdempotencyKey: "has space", IfMatch: `"impact"`},
		{IdempotencyKey: "remove-1"},
		{IdempotencyKey: "remove-1", IfMatch: "  "},
		{IdempotencyKey: "remove-1", IfMatch: "\"impact\"\r\nX-Injected: 1"},
	} {
		if _, err := client.Remove(context.Background(), "worker-1", options); err == nil {
			t.Fatalf("Remove(%#v) succeeded", options)
		}
	}
	if requests.Load() != 0 {
		t.Fatalf("%d invalid removals reached the server", requests.Load())
	}
}

func TestRemoveRefusalIsAWorkerAPIError(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		w.WriteHeader(http.StatusPreconditionFailed)
		_, _ = io.WriteString(w, `{"code":"PRECONDITION_FAILED","message":"impact changed","requestId":"req-412"}`)
	}))
	defer server.Close()
	_, err := newTestClient(t, server, true).Remove(context.Background(), "worker-1", RemoveOptions{IdempotencyKey: "remove-1", IfMatch: `"stale"`})
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusPreconditionFailed || apiErr.Code != "PRECONDITION_FAILED" || attempts.Load() != 1 {
		t.Fatalf("Remove() error = %#v after %d attempts", err, attempts.Load())
	}
}

func TestIfMatchIsSentOnlyWhereDeclared(t *testing.T) {
	var ifMatch atomic.Value
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ifMatch.Store(r.Header.Get("If-Match"))
		_, _ = io.WriteString(w, `{}`)
	}))
	defer server.Close()
	headers := http.Header{"Idempotency-Key": {"upgrade-1"}, "If-Match": {`"impact"`}}
	if err := newTestClient(t, server, false).OpenAPI().Do(context.Background(), "upgradeWorker", map[string]string{"workerId": "worker-1"}, nil, headers, nil, nil); err != nil {
		t.Fatal(err)
	}
	if got := ifMatch.Load(); got != "" {
		t.Fatalf("upgradeWorker forwarded If-Match %q", got)
	}
}
