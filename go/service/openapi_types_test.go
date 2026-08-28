package service

import (
	"encoding/json"
	"testing"
	"time"
)

func TestServiceRepositoryExposesAutomaticDeploymentWiring(t *testing.T) {
	checkedAt := time.Date(2026, 8, 28, 20, 0, 0, 0, time.UTC)
	repository := OpenAPIServiceRepository{
		Provider: "gitlab", RepoOwner: "postgrip", RepoName: "api", DefaultBranch: "main",
		AutomaticDeployments: OpenAPIServiceAutomaticDeploymentWiring{
			Active: false, Status: "provider-unsupported", CheckedAt: checkedAt,
		},
	}
	encoded, err := json.Marshal(repository)
	if err != nil {
		t.Fatal(err)
	}
	var wire map[string]any
	if err := json.Unmarshal(encoded, &wire); err != nil {
		t.Fatal(err)
	}
	wiring, ok := wire["automaticDeployments"].(map[string]any)
	if !ok || wiring["status"] != "provider-unsupported" || wiring["active"] != false {
		t.Fatalf("automaticDeployments=%v", wire["automaticDeployments"])
	}
}

func TestPostGripConfigurationWorkerSelectorIsClosed(t *testing.T) {
	id := "11111111-1111-4111-8111-111111111111"
	encoded, err := json.Marshal(OpenAPIPostGripConfigurationWorkerSelector{Id: &id})
	if err != nil || string(encoded) != `{"id":"11111111-1111-4111-8111-111111111111"}` {
		t.Fatalf("marshal selector=%s err=%v", encoded, err)
	}
	for _, invalid := range []string{
		`{}`,
		`{"id":"11111111-1111-4111-8111-111111111111","name":"worker-west"}`,
		`{"name":"worker-west","unexpected":true}`,
	} {
		var selector OpenAPIPostGripConfigurationWorkerSelector
		if err := json.Unmarshal([]byte(invalid), &selector); err == nil {
			t.Fatalf("invalid selector was accepted: %s", invalid)
		}
	}
}
