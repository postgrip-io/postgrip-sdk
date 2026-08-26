package postgrip

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/postgrip-io/postgrip-agent-sdks/go/service"
	"github.com/postgrip-io/postgrip-agent-sdks/go/worker"
)

func TestUnifiedClientUsesOneTokenForEveryPlane(t *testing.T) {
	const token = "pgt_one-token"
	seen := map[string]string{}
	var mu sync.Mutex
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		seen[r.URL.Path] = r.Header.Get("Authorization")
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/readyz":
			_, _ = w.Write([]byte(`{"status":"ready","stats":{}}`))
		case "/api/v1/workers":
			_, _ = w.Write([]byte(`{"items":[]}`))
		case "/api/v1/services":
			_, _ = w.Write([]byte(`{"items":[],"nextCursor":""}`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	client, err := New(Config{BaseURL: server.URL, Token: token, HTTPClient: server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := client.Agent.Connection.OpenAPI().Ready(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Workers.List(ctx, worker.ListWorkersOptions{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Services.List(ctx, service.OpenAPIListServicesQuery{}); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{"/readyz", "/api/v1/workers", "/api/v1/services"} {
		if got := seen[path]; got != "Bearer "+token {
			t.Fatalf("%s Authorization=%q", path, got)
		}
	}
}

func TestNewFromEnvUsesCommonAndPlaneURLPrecedence(t *testing.T) {
	t.Setenv("POSTGRIP_URL", "https://common.example.test")
	t.Setenv("POSTGRIP_AGENT_URL", "https://agent.example.test")
	t.Setenv("POSTGRIP_TOKEN", "pgt_environment")
	client, err := NewFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if client.Agent.Connection.Address() != "https://agent.example.test" {
		t.Fatalf("Agent URL=%q", client.Agent.Connection.Address())
	}
}
