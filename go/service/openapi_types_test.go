package service

import (
	"encoding/json"
	"testing"
)

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
