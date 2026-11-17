package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSandboxUpdatePreservesOmissionAndEmptyLabels(t *testing.T) {
	for _, clear := range []bool{false, true} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != "PATCH" || r.URL.Path != "/api/v1/sandboxes/sbx_test" || r.Header.Get("Authorization") != "Bearer pgt_test" {
				t.Errorf("request: %s %s %s", r.Method, r.URL.Path, r.Header.Get("Authorization"))
			}
			var body map[string]json.RawMessage
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
			}
			labels, present := body["labels"]
			if present != clear || (clear && string(labels) != "{}") {
				t.Errorf("labels=%s present=%v clear=%v", labels, present, clear)
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"id":"sbx_test","name":"changed"}`))
		}))
		connection, err := NewConnection(ConnectionOptions{Address: server.URL, AuthToken: "pgt_test", InsecureDevelopment: true})
		if err != nil {
			t.Fatal(err)
		}
		name := "changed"
		body := OpenAPIUpdateSandboxRequestBody{Name: &name}
		if clear {
			labels := map[string]string{}
			body.Labels = &labels
		}
		result, err := connection.OpenAPI().UpdateSandbox(context.Background(), "sbx_test", body)
		server.Close()
		if err != nil || result.Name != name {
			t.Fatalf("result=%+v err=%v", result, err)
		}
	}
}

func TestAgentEnrollmentSendsOnlyOneTimeCredential(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/api/v1/agent/enroll" || r.Header.Get("Authorization") != "" {
			t.Errorf("enrollment leaked management authentication")
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if body["enrollmentKey"] != "test-one-time-key" {
			t.Errorf("body=%v", body)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(201)
		_, _ = w.Write([]byte(`{"agentId":"agent-created"}`))
	}))
	defer server.Close()
	connection, err := NewConnection(ConnectionOptions{Address: server.URL, AuthToken: "pgt_test", InsecureDevelopment: true})
	if err != nil {
		t.Fatal(err)
	}
	result, err := connection.OpenAPI().EnrollAgent(context.Background(), OpenAPIEnrollAgentRequestBody{EnrollmentKey: "test-one-time-key"})
	if err != nil || result.AgentID != "agent-created" {
		t.Fatalf("result=%+v err=%v", result, err)
	}
}
