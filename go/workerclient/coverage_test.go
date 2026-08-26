package workerclient

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestEveryWorkerFacadeUsesItsCanonicalRoute(t *testing.T) {
	t.Parallel()
	var mu sync.Mutex
	seen := map[string]int{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		seen[r.Method+" "+r.URL.Path]++
		mu.Unlock()
		if r.URL.Path != "/health" && r.Header.Get("Authorization") != "Bearer pgwm_test-token" {
			t.Fatalf("authorization=%q for %s", r.Header.Get("Authorization"), r.URL.Path)
		}
		if r.Method == http.MethodPost && r.Header.Get("Idempotency-Key") != "operation-1" {
			t.Fatalf("idempotency=%q for %s", r.Header.Get("Idempotency-Key"), r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/health":
			_, _ = fmt.Fprint(w, `{"status":"ok"}`)
		case r.URL.Path == "/api/v1/workers":
			_, _ = fmt.Fprint(w, `{"items":[]}`)
		case r.URL.Path == "/api/v1/workers/worker-1/assignments":
			_, _ = fmt.Fprint(w, `{"items":[]}`)
		case r.URL.Path == "/api/v1/workers/worker-1/jobs":
			_, _ = fmt.Fprint(w, `{"items":[]}`)
		case r.URL.Path == "/api/v1/workers/worker-1/operational-logs" || r.URL.Path == "/api/v1/workers/worker-1/security-logs":
			_, _ = fmt.Fprint(w, `{"items":[],"nextCursor":""}`)
		default:
			_, _ = fmt.Fprint(w, `{}`)
		}
	}))
	defer server.Close()
	client := newTestClient(t, server, false)
	ctx := context.Background()

	if _, err := client.Health(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Get(ctx, "worker-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Assignments(ctx, "worker-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Jobs(ctx, "worker-1", OpenAPIListWorkerJobsQuery{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Job(ctx, "worker-1", "job-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.OperationalLogs(ctx, "worker-1", OpenAPIListWorkerOperationalLogsQuery{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.SecurityLogs(ctx, "worker-1", OpenAPIListWorkerSecurityLogsQuery{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Check(ctx, "worker-1", "operation-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Maintenance(ctx, "worker-1", "operation-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Resume(ctx, "worker-1", "operation-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Upgrade(ctx, "worker-1", "operation-1"); err != nil {
		t.Fatal(err)
	}

	for _, route := range []string{
		"GET /health", "GET /api/v1/workers/worker-1", "GET /api/v1/workers/worker-1/assignments",
		"GET /api/v1/workers/worker-1/jobs", "GET /api/v1/workers/worker-1/jobs/job-1",
		"GET /api/v1/workers/worker-1/operational-logs", "GET /api/v1/workers/worker-1/security-logs",
		"POST /api/v1/workers/worker-1/check", "POST /api/v1/workers/worker-1/maintenance",
		"POST /api/v1/workers/worker-1/maintenance/resume", "POST /api/v1/workers/worker-1/upgrade",
	} {
		if seen[route] == 0 {
			t.Errorf("route %s was not exercised", route)
		}
	}
}

func TestWorkerAndJobPagersPreserveOpaqueTokens(t *testing.T) {
	t.Parallel()
	var workers, jobs atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/workers":
			if workers.Add(1) == 1 {
				_, _ = fmt.Fprint(w, `{"items":[],"nextPageToken":"worker-next"}`)
				return
			}
			if r.URL.Query().Get("pageToken") != "worker-next" {
				t.Fatalf("worker page token=%q", r.URL.Query().Get("pageToken"))
			}
			_, _ = fmt.Fprint(w, `{"items":[],"nextPageToken":null}`)
		case "/api/v1/workers/worker-1/jobs":
			if jobs.Add(1) == 1 {
				_, _ = fmt.Fprint(w, `{"items":[],"nextPageToken":"job-next"}`)
				return
			}
			if r.URL.Query().Get("pageToken") != "job-next" {
				t.Fatalf("job page token=%q", r.URL.Query().Get("pageToken"))
			}
			_, _ = fmt.Fprint(w, `{"items":[],"nextPageToken":null}`)
		default:
			t.Fatalf("unexpected path=%s", r.URL.Path)
		}
	}))
	defer server.Close()
	client := newTestClient(t, server, false)
	workerPager := client.Workers(ListWorkersOptions{})
	if !workerPager.Next(context.Background()) || !workerPager.Next(context.Background()) || workerPager.Next(context.Background()) || workerPager.Err() != nil {
		t.Fatalf("worker pager page=%#v err=%v", workerPager.Page(), workerPager.Err())
	}
	jobPager := client.WorkerJobs("worker-1", OpenAPIListWorkerJobsQuery{})
	if !jobPager.Next(context.Background()) || !jobPager.Next(context.Background()) || jobPager.Next(context.Background()) || jobPager.Err() != nil {
		t.Fatalf("job pager page=%#v err=%v", jobPager.Page(), jobPager.Err())
	}
}

func TestSecurityLogIteratorDeduplicatesAndCancels(t *testing.T) {
	t.Parallel()
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if requests.Add(1) == 1 {
			_, _ = fmt.Fprint(w, `{"items":[{"id":1}],"nextCursor":"first"}`)
			return
		}
		_, _ = fmt.Fprint(w, `{"items":[{"id":1},{"id":2}],"nextCursor":"second"}`)
	}))
	defer server.Close()
	iterator := newTestClient(t, server, false).FollowSecurityLogs("worker-1", OpenAPIListWorkerSecurityLogsQuery{})
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if !iterator.Next(ctx) || iterator.Entry().Id != 1 {
		t.Fatalf("first entry=%#v err=%v", iterator.Entry(), iterator.Err())
	}
	if !iterator.Next(ctx) || iterator.Entry().Id != 2 {
		t.Fatalf("second entry=%#v err=%v", iterator.Entry(), iterator.Err())
	}
	cancel()
	if iterator.Next(ctx) || iterator.Err() == nil {
		t.Fatalf("canceled iterator err=%v", iterator.Err())
	}
}
