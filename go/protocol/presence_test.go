package protocol

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
	"time"
)

// generic decodes JSON into plain maps and slices for semantic comparison.
func generic(t *testing.T, data string) any {
	t.Helper()
	var value any
	if err := json.Unmarshal([]byte(data), &value); err != nil {
		t.Fatalf("decode %s: %v", data, err)
	}
	return value
}

func mustJSON(t *testing.T, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded)
}

// withMember returns a JSON object with one more member.
func withMember(object, name, value string) string {
	if object == "{}" {
		return "{" + `"` + name + `":` + value + "}"
	}
	return strings.TrimSuffix(object, "}") + `,"` + name + `":` + value + "}"
}

// roundTrip decodes input into a fresh T, re-encodes it and requires the same
// JSON: absent members stay absent, explicit nulls stay null, values keep.
func roundTrip[T any](t *testing.T, input string) {
	t.Helper()
	var value T
	if err := json.Unmarshal([]byte(input), &value); err != nil {
		t.Fatalf("decode %s: %v", input, err)
	}
	if got := mustJSON(t, value); !reflect.DeepEqual(generic(t, got), generic(t, input)) {
		t.Fatalf("round trip changed the JSON:\n got %s\nwant %s", got, input)
	}
}

func canonicalSandbox(t *testing.T) string {
	created := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	return mustJSON(t, Sandbox{
		TenantID: "tenant", ID: "sbx_1", Name: "box", CreatedBy: "user", DesiredState: "running",
		ObservedState: "running", Generation: 2, ObservedGeneration: 2, Backend: "docker",
		IsolationClass: "standard", Image: "alpine", CreatedAt: created, UpdatedAt: created,
		NetworkPolicy: SandboxNetworkPolicy{DenyHostAccess: true},
	})
}

// The presence round-trip table: absent, null and a value for each of the six
// optional nullable properties, and absent and present for each of the four
// optional struct properties, round-trip unchanged.
func TestPresenceRoundTripTable(t *testing.T) {
	task := mustJSON(t, Task{ID: "task-1", Namespace: "default", Queue: "q", Type: "activity:A", State: "queued"})
	sandbox := canonicalSandbox(t)
	timestamp := `"2026-01-02T03:04:05Z"`
	cases := map[string]func(*testing.T){
		"PollTaskResponse.task absent": func(t *testing.T) { roundTrip[PollTaskResponse](t, `{}`) },
		"PollTaskResponse.task null":   func(t *testing.T) { roundTrip[PollTaskResponse](t, `{"task":null}`) },
		"PollTaskResponse.task value":  func(t *testing.T) { roundTrip[PollTaskResponse](t, withMember("{}", "task", task)) },
		"TaskResult.value absent":      func(t *testing.T) { roundTrip[TaskResult](t, `{"message":"m"}`) },
		"TaskResult.value null":        func(t *testing.T) { roundTrip[TaskResult](t, `{"value":null}`) },
		"TaskResult.value value":       func(t *testing.T) { roundTrip[TaskResult](t, `{"value":{"ok":true}}`) },
		"TaskResult.started_at absent": func(t *testing.T) { roundTrip[TaskResult](t, `{"value":1}`) },
		"TaskResult.started_at present": func(t *testing.T) {
			roundTrip[TaskResult](t, withMember("{}", "started_at", timestamp))
		},
		"TaskResult.finished_at absent": func(t *testing.T) { roundTrip[TaskResult](t, `{"exit_code":2}`) },
		"TaskResult.finished_at present": func(t *testing.T) {
			roundTrip[TaskResult](t, withMember("{}", "finished_at", timestamp))
		},
		"SandboxCreateRequest.resourceLimits absent": func(t *testing.T) { roundTrip[SandboxCreateRequest](t, `{"name":"s"}`) },
		"SandboxCreateRequest.resourceLimits present": func(t *testing.T) {
			roundTrip[SandboxCreateRequest](t, `{"name":"s","resourceLimits":{"cpus":0.5}}`)
		},
		"SandboxCreateRequest.networkPolicy absent": func(t *testing.T) { roundTrip[SandboxCreateRequest](t, `{"name":"s","image":"alpine"}`) },
		"SandboxCreateRequest.networkPolicy present": func(t *testing.T) {
			roundTrip[SandboxCreateRequest](t, `{"name":"s","networkPolicy":{"internetEgress":false,"denyHostAccess":true}}`)
		},
	}
	for _, name := range []string{"expiresAt", "lastActivityAt", "stoppedAt", "deletedAt"} {
		cases["Sandbox."+name+" absent"] = func(t *testing.T) { roundTrip[Sandbox](t, sandbox) }
		cases["Sandbox."+name+" null"] = func(t *testing.T) { roundTrip[Sandbox](t, withMember(sandbox, name, "null")) }
		cases["Sandbox."+name+" value"] = func(t *testing.T) { roundTrip[Sandbox](t, withMember(sandbox, name, timestamp)) }
	}
	for name, run := range cases {
		t.Run(name, run)
	}
}

// Decoding replaces the whole value, so nothing from an earlier decode into the
// same variable survives: neither a field nor a presence bit.
func TestPresenceDecodingIntoAReusedValue(t *testing.T) {
	var poll PollTaskResponse
	for _, input := range []string{`{"task":null}`, `{}`} {
		if err := json.Unmarshal([]byte(input), &poll); err != nil {
			t.Fatal(err)
		}
	}
	if got := mustJSON(t, poll); got != `{}` {
		t.Fatalf("null then absent = %s, want {}", got)
	}

	var result TaskResult
	for _, input := range []string{`{"value":1,"started_at":"2026-01-02T03:04:05Z"}`, `{}`} {
		if err := json.Unmarshal([]byte(input), &result); err != nil {
			t.Fatal(err)
		}
	}
	if got := mustJSON(t, result); got != `{}` {
		t.Fatalf("value and present timestamp then absent = %s, want {}", got)
	}

	var request SandboxCreateRequest
	for _, input := range []string{`{"name":"a","resourceLimits":{"cpus":1}}`, `{"name":"b"}`} {
		if err := json.Unmarshal([]byte(input), &request); err != nil {
			t.Fatal(err)
		}
	}
	if got := mustJSON(t, request); got != `{"name":"b"}` {
		t.Fatalf("present struct then absent = %s, want {\"name\":\"b\"}", got)
	}

	sandbox := canonicalSandbox(t)
	var decoded Sandbox
	for _, input := range []string{withMember(sandbox, "stoppedAt", "null"), sandbox} {
		if err := json.Unmarshal([]byte(input), &decoded); err != nil {
			t.Fatal(err)
		}
	}
	if got := mustJSON(t, decoded); strings.Contains(got, "stoppedAt") {
		t.Fatalf("null then absent kept stoppedAt: %s", got)
	}
}

// A value built in code has no presence record and encodes byte for byte as
// the type did before it had JSON methods.
func TestConstructedValuesEncodeAsBefore(t *testing.T) {
	type legacyPollTaskResponse PollTaskResponse
	type legacySandbox Sandbox
	type legacyTaskResult TaskResult
	type legacySandboxCreateRequest SandboxCreateRequest
	started := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	stopped := started.Add(time.Hour)
	cases := []struct {
		name           string
		current, prior any
	}{
		{"empty PollTaskResponse", PollTaskResponse{}, legacyPollTaskResponse{}},
		{"PollTaskResponse with directive", PollTaskResponse{Directive: &AgentPollDirective{Type: "shutdown"}}, legacyPollTaskResponse{Directive: &AgentPollDirective{Type: "shutdown"}}},
		{"empty TaskResult keeps zero timestamps", TaskResult{}, legacyTaskResult{}},
		{"TaskResult", TaskResult{Value: "v", StartedAt: started}, legacyTaskResult{Value: "v", StartedAt: started}},
		{"minimal SandboxCreateRequest keeps zero structs", SandboxCreateRequest{Name: "s"}, legacySandboxCreateRequest{Name: "s"}},
		{"Sandbox", Sandbox{ID: "sbx", StoppedAt: &stopped}, legacySandbox{ID: "sbx", StoppedAt: &stopped}},
	}
	for _, c := range cases {
		if got, want := mustJSON(t, c.current), mustJSON(t, c.prior); got != want {
			t.Fatalf("%s encodes %s, want %s", c.name, got, want)
		}
	}
	if got := mustJSON(t, SandboxCreateRequest{Name: "s"}); !strings.Contains(got, `"resourceLimits":{}`) || !strings.Contains(got, `"networkPolicy":{`) {
		t.Fatalf("a constructed request lost its zero-valued structs: %s", got)
	}
}

// A request decoded from JSON without the optional structs sends neither.
func TestDecodedSandboxCreateRequestOmitsAbsentStructs(t *testing.T) {
	var request SandboxCreateRequest
	if err := json.Unmarshal([]byte(`{"name":"s","image":"alpine"}`), &request); err != nil {
		t.Fatal(err)
	}
	if got := mustJSON(t, request); got != `{"name":"s","image":"alpine"}` {
		t.Fatalf("decoded request sends %s", got)
	}
}

// The JSON methods are promoted to a struct that anonymously embeds one of
// these types, in both directions: the wrapper's own fields are neither
// encoded nor decoded. This documents the behavior so it only changes
// deliberately.
func TestPresenceMethodsArePromotedThroughEmbedding(t *testing.T) {
	type wrapper struct {
		PollTaskResponse
		Extra string `json:"extra"`
	}
	if got := mustJSON(t, wrapper{Extra: "kept?"}); got != `{}` {
		t.Fatalf("embedding wrapper encodes %s, want the promoted {} without extra", got)
	}
	var decoded wrapper
	if err := json.Unmarshal([]byte(`{"task":null,"extra":"set?"}`), &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Extra != "" {
		t.Fatalf("embedding wrapper decoded extra = %q, want it unset by the promoted method", decoded.Extra)
	}
}
