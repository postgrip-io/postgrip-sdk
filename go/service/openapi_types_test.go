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

func TestGeneratedRequiredAlternativesValidateOnRoundTrip(t *testing.T) {
	tests := []struct {
		name        string
		newValue    func() any
		validJSON   []string
		invalidJSON string
	}{
		{
			name:     "release group member",
			newValue: func() any { return &OpenAPIServiceReleaseGroupMemberRequest{} },
			validJSON: []string{
				`{"expectedCommitSha":"abc123","branch":"main"}`,
				`{"sourceDeploymentId":"deployment-1","expectedArtifactIdentity":"sha256:abc"}`,
			},
			invalidJSON: `{}`,
		},
		{
			name:     "repository adoption preview",
			newValue: func() any { return &OpenAPIGitHubRepositoryAdoptionPreviewRequest{} },
			validJSON: []string{
				`{"repositoryId":1,"automaticDeployments":true}`,
				`{"repository":"postgrip/api","automaticDeployments":false}`,
			},
			invalidJSON: `{"repositoryId":1,"repository":"postgrip/api"}`,
		},
		{
			name:        "traffic status result",
			newValue:    func() any { return &OpenAPIServiceTrafficStatusWorkerResult{} },
			validJSON:   []string{`{"data":{}}`, `{"error":{"code":"FAILED","message":"failed"}}`},
			invalidJSON: `{"data":{},"error":{"code":"FAILED","message":"failed"}}`,
		},
		{
			name:        "traffic report result",
			newValue:    func() any { return &OpenAPIServiceTrafficReportWorkerResult{} },
			validJSON:   []string{`{"data":{}}`, `{"error":{"code":"FAILED","message":"failed"}}`},
			invalidJSON: `{"data":{},"error":{"code":"FAILED","message":"failed"}}`,
		},
		{
			name:        "traffic settings result",
			newValue:    func() any { return &OpenAPIServiceTrafficSettingsWorkerResult{} },
			validJSON:   []string{`{"data":{}}`, `{"error":{"code":"FAILED","message":"failed"}}`},
			invalidJSON: `{"data":{},"error":{"code":"FAILED","message":"failed"}}`,
		},
		{
			name:        "traffic maintenance result",
			newValue:    func() any { return &OpenAPIServiceTrafficMaintenanceWorkerResult{} },
			validJSON:   []string{`{"data":{}}`, `{"error":{"code":"FAILED","message":"failed"}}`},
			invalidJSON: `{"data":{},"error":{"code":"FAILED","message":"failed"}}`,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			for _, input := range test.validJSON {
				value := test.newValue()
				if err := json.Unmarshal([]byte(input), value); err != nil {
					t.Fatalf("valid input %s: %v", input, err)
				}
				if _, err := json.Marshal(value); err != nil {
					t.Fatalf("marshal valid input %s: %v", input, err)
				}
			}

			value := test.newValue()
			if err := json.Unmarshal([]byte(test.invalidJSON), value); err == nil {
				t.Fatalf("invalid input was accepted: %s", test.invalidJSON)
			}
		})
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

func TestUpdateServiceEnvironmentPreservesEmptyVolumeReplacement(t *testing.T) {
	volumes := []OpenAPIServiceEphemeralVolumeMountInput{}
	encoded, err := json.Marshal(OpenAPIUpdateServiceEnvironmentRequest{Volumes: &volumes})
	if err != nil {
		t.Fatal(err)
	}
	if string(encoded) != `{"volumes":[]}` {
		t.Fatalf("empty volume replacement=%s", encoded)
	}
}

func TestPostGripConfigurationEnvironmentSupportsAutomaticPlacement(t *testing.T) {
	environment := OpenAPIPostGripConfigurationEnvironment{
		Ref: "production", Name: "Production", Kind: "production",
		Domains: []OpenAPIPostGripConfigurationDomain{}, Variables: []OpenAPIPostGripConfigurationVariable{},
	}
	encoded, err := json.Marshal(environment)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(encoded, []byte(`"assignedWorker"`)) {
		t.Fatalf("automatic declarative placement emitted assignedWorker: %s", encoded)
	}
	if bytes.Contains(encoded, []byte(`"containerPort"`)) {
		t.Fatalf("portless declarative environment emitted containerPort: %s", encoded)
	}
}
