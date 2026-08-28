package service

import (
	"bytes"
	"encoding/json"
	"testing"
	"time"
)

func TestServiceRepositoryExposesAutomaticDeploymentWiring(t *testing.T) {
	checkedAt := time.Date(2026, 8, 28, 20, 0, 0, 0, time.UTC)
	repository := OpenAPIServiceRepository{
		Provider: "gitlab", RepoOwner: "postgrip", RepoName: "api", DefaultBranch: "main",
		AutomaticDeployments: OpenAPIServiceAutomaticDeploymentWiring{
			Active: false, Status: OpenAPIServiceAutomaticDeploymentWiringStatusProviderUnsupported, CheckedAt: checkedAt,
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

func TestServiceEnvironmentSupportsAutomaticPlacement(t *testing.T) {
	request := OpenAPICreateServiceEnvironmentRequest{Name: "Production", Kind: "production"}
	encoded, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	if string(encoded) != `{"name":"Production","kind":"production"}` {
		t.Fatalf("automatic placement request=%s", encoded)
	}
	placement := OpenAPIServiceEnvironmentPlacement{
		WorkerId: "11111111-1111-4111-8111-111111111111",
		Mode:     "automatic",
		Reason:   "most-recent-eligible",
	}
	encoded, err = json.Marshal(placement)
	if err != nil || string(encoded) != `{"workerId":"11111111-1111-4111-8111-111111111111","mode":"automatic","reason":"most-recent-eligible"}` {
		t.Fatalf("placement=%s err=%v", encoded, err)
	}
}

func TestPostGripConfigurationEnvironmentSupportsAutomaticPlacement(t *testing.T) {
	environment := OpenAPIPostGripConfigurationEnvironment{
		Ref: "production", Name: "Production", Kind: "production", ContainerPort: 3000,
		Domains: []OpenAPIPostGripConfigurationDomain{}, Variables: []OpenAPIPostGripConfigurationVariable{},
	}
	encoded, err := json.Marshal(environment)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(encoded, []byte(`"assignedWorker"`)) {
		t.Fatalf("automatic declarative placement emitted assignedWorker: %s", encoded)
	}
}
