package worker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGeneratedWorkerUpdateUsesKeyAndPreservesOmittedHost(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "PUT" || r.URL.Path != "/api/v1/workers/worker-one" || r.Header.Get("Idempotency-Key") != "update-one" {
			t.Errorf("wrong update request")
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if len(body) != 1 || body["name"] != "renamed" {
			t.Errorf("body=%v", body)
		}
		_, _ = w.Write([]byte(`{"id":"worker-one","name":"renamed"}`))
	}))
	defer server.Close()
	client := newTestClient(t, server, false)
	response, err := client.OpenAPI().UpdateWorker(context.Background(), "worker-one", OpenAPIUpdateWorkerHeaders{IdempotencyKey: "update-one"}, OpenAPIUpdateWorkerRequestBody{Name: "renamed"})
	if err != nil || response.Name != "renamed" {
		t.Fatalf("response=%+v err=%v", response, err)
	}
}
