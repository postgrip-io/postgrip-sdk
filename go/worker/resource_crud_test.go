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

func TestGeneratedWorkerUpdateMaintenanceWindowEnableAndDisable(t *testing.T) {
	start, duration, timezone := int64(60), int64(30), "UTC"
	for _, enabled := range []bool{true, false} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
			}
			window, ok := body["maintenanceWindow"].(map[string]any)
			if !ok || window["enabled"] != enabled {
				t.Errorf("window=%v", window)
			}
			if enabled && (window["startMinute"] != float64(start) || window["durationMinutes"] != float64(duration) || window["timezone"] != timezone) {
				t.Errorf("window=%v", window)
			}
			_, _ = w.Write([]byte(`{"id":"worker-one","name":"renamed"}`))
		}))
		window := OpenAPIWorkerMaintenanceWindowInput{Enabled: enabled}
		if enabled {
			window.StartMinute = &start
			window.DurationMinutes = &duration
			window.Timezone = &timezone
		}
		client := newTestClient(t, server, false)
		_, err := client.OpenAPI().UpdateWorker(context.Background(), "worker-one", OpenAPIUpdateWorkerHeaders{IdempotencyKey: "window"}, OpenAPIUpdateWorkerRequestBody{Name: "renamed", MaintenanceWindow: &window})
		server.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
}
