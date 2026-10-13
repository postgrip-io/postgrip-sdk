package protocol

import (
	"bytes"
	"encoding/json"
	"reflect"
	"strings"
)

// presence records what a value decoded from JSON held for the properties a
// plain Go field cannot represent: which optional nullable properties were an
// explicit null, and which optional struct properties were present at all. A
// value built in code has no presenceDecoded bit and encodes exactly as before.
// The record is a bitmask, so types that are comparable stay comparable.
type presence uint16

const presenceDecoded presence = 1

// Bits for each type's properties. Only one type's bits are ever set in one
// record, so they may share values across types.
const (
	pollTaskNull presence = 1 << (iota + 1)
)

const (
	sandboxExpiresAtNull presence = 1 << (iota + 1)
	sandboxLastActivityAtNull
	sandboxStoppedAtNull
	sandboxDeletedAtNull
)

const (
	taskResultValueNull presence = 1 << (iota + 1)
	taskResultStartedAtPresent
	taskResultFinishedAtPresent
)

const (
	sandboxCreateResourceLimitsPresent presence = 1 << (iota + 1)
	sandboxCreateNetworkPolicyPresent
)

// PollTaskResponse and TaskResult were comparable before presence handling
// and must stay comparable, including as map keys.
func _() {
	_ = PollTaskResponse{} == PollTaskResponse{}
	_ = TaskResult{} == TaskResult{}
}

// decodeMembers decodes data into target and returns its top-level members.
// It returns nil members for the literal null, which leaves target unchanged,
// as encoding/json does for a struct.
func decodeMembers(data []byte, target any) (map[string]json.RawMessage, error) {
	if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return nil, nil
	}
	if err := json.Unmarshal(data, target); err != nil {
		return nil, err
	}
	var members map[string]json.RawMessage
	if err := json.Unmarshal(data, &members); err != nil {
		return nil, err
	}
	return members, nil
}

// isNull reports whether a member was present as an explicit null.
func isNull(member json.RawMessage) bool {
	return member != nil && bytes.Equal(bytes.TrimSpace(member), []byte("null"))
}

// jsonFieldNames returns the JSON names of a struct type's serialized fields in
// declaration order, which is the order encoding/json writes them.
func jsonFieldNames(t reflect.Type) []string {
	names := make([]string, 0, t.NumField())
	for i := range t.NumField() {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}
		name, _, _ := strings.Cut(field.Tag.Get("json"), ",")
		if name == "-" {
			continue
		}
		if name == "" {
			name = field.Name
		}
		names = append(names, name)
	}
	return names
}

// rewriteMembers re-emits an encoded object in field order, writing an
// explicit null for each name in nulls that the encoding omitted and dropping
// each name in omit. Everything else keeps its encoded bytes.
func rewriteMembers(encoded []byte, order []string, nulls, omit map[string]bool) ([]byte, error) {
	var members map[string]json.RawMessage
	if err := json.Unmarshal(encoded, &members); err != nil {
		return nil, err
	}
	var out bytes.Buffer
	out.WriteByte('{')
	write := func(name string, value []byte) {
		if out.Len() > 1 {
			out.WriteByte(',')
		}
		key, _ := json.Marshal(name)
		out.Write(key)
		out.WriteByte(':')
		out.Write(value)
	}
	for _, name := range order {
		if omit[name] {
			continue
		}
		if value, ok := members[name]; ok {
			write(name, value)
		} else if nulls[name] {
			write(name, []byte("null"))
		}
	}
	out.WriteByte('}')
	return out.Bytes(), nil
}

var (
	pollTaskResponseFieldNames     = jsonFieldNames(reflect.TypeFor[PollTaskResponse]())
	sandboxFieldNames              = jsonFieldNames(reflect.TypeFor[Sandbox]())
	taskResultFieldNames           = jsonFieldNames(reflect.TypeFor[TaskResult]())
	sandboxCreateRequestFieldNames = jsonFieldNames(reflect.TypeFor[SandboxCreateRequest]())
)

// MarshalJSON writes an explicit "task": null when the value was decoded with
// one, and otherwise encodes as before.
func (r PollTaskResponse) MarshalJSON() ([]byte, error) {
	type wire PollTaskResponse
	encoded, err := json.Marshal(wire(r))
	if err != nil || r.presence&presenceDecoded == 0 {
		return encoded, err
	}
	nulls := map[string]bool{"task": r.Task == nil && r.presence&pollTaskNull != 0}
	return rewriteMembers(encoded, pollTaskResponseFieldNames, nulls, nil)
}

// UnmarshalJSON decodes into a fresh value and records an explicit "task": null.
func (r *PollTaskResponse) UnmarshalJSON(data []byte) error {
	type wire PollTaskResponse
	var decoded wire
	members, err := decodeMembers(data, &decoded)
	if err != nil || members == nil {
		return err
	}
	decoded.presence = presenceDecoded
	if isNull(members["task"]) {
		decoded.presence |= pollTaskNull
	}
	*r = PollTaskResponse(decoded)
	return nil
}

// MarshalJSON writes an explicit null for each nullable timestamp the value
// was decoded with as null, and otherwise encodes as before.
func (s Sandbox) MarshalJSON() ([]byte, error) {
	type wire Sandbox
	encoded, err := json.Marshal(wire(s))
	if err != nil || s.presence&presenceDecoded == 0 {
		return encoded, err
	}
	nulls := map[string]bool{
		"expiresAt":      s.ExpiresAt == nil && s.presence&sandboxExpiresAtNull != 0,
		"lastActivityAt": s.LastActivityAt == nil && s.presence&sandboxLastActivityAtNull != 0,
		"stoppedAt":      s.StoppedAt == nil && s.presence&sandboxStoppedAtNull != 0,
		"deletedAt":      s.DeletedAt == nil && s.presence&sandboxDeletedAtNull != 0,
	}
	return rewriteMembers(encoded, sandboxFieldNames, nulls, nil)
}

// UnmarshalJSON decodes into a fresh value and records each explicit null.
func (s *Sandbox) UnmarshalJSON(data []byte) error {
	type wire Sandbox
	var decoded wire
	members, err := decodeMembers(data, &decoded)
	if err != nil || members == nil {
		return err
	}
	decoded.presence = presenceDecoded
	for name, bit := range map[string]presence{
		"expiresAt":      sandboxExpiresAtNull,
		"lastActivityAt": sandboxLastActivityAtNull,
		"stoppedAt":      sandboxStoppedAtNull,
		"deletedAt":      sandboxDeletedAtNull,
	} {
		if isNull(members[name]) {
			decoded.presence |= bit
		}
	}
	*s = Sandbox(decoded)
	return nil
}

// MarshalJSON writes an explicit "value": null when the value was decoded with
// one, and omits started_at and finished_at when a decoded value lacked them
// and they are still zero. A value built in code encodes as before.
func (r TaskResult) MarshalJSON() ([]byte, error) {
	type wire TaskResult
	encoded, err := json.Marshal(wire(r))
	if err != nil || r.presence&presenceDecoded == 0 {
		return encoded, err
	}
	nulls := map[string]bool{"value": r.Value == nil && r.presence&taskResultValueNull != 0}
	omit := map[string]bool{
		"started_at":  r.presence&taskResultStartedAtPresent == 0 && r.StartedAt.IsZero(),
		"finished_at": r.presence&taskResultFinishedAtPresent == 0 && r.FinishedAt.IsZero(),
	}
	return rewriteMembers(encoded, taskResultFieldNames, nulls, omit)
}

// UnmarshalJSON decodes into a fresh value and records an explicit null value
// and which timestamps were present.
func (r *TaskResult) UnmarshalJSON(data []byte) error {
	type wire TaskResult
	var decoded wire
	members, err := decodeMembers(data, &decoded)
	if err != nil || members == nil {
		return err
	}
	decoded.presence = presenceDecoded
	if isNull(members["value"]) {
		decoded.presence |= taskResultValueNull
	}
	if _, ok := members["started_at"]; ok {
		decoded.presence |= taskResultStartedAtPresent
	}
	if _, ok := members["finished_at"]; ok {
		decoded.presence |= taskResultFinishedAtPresent
	}
	*r = TaskResult(decoded)
	return nil
}

// MarshalJSON omits resourceLimits and networkPolicy when a decoded value
// lacked them and they are still zero, so values assigned after decoding are
// sent. A value built in code encodes as before.
func (r SandboxCreateRequest) MarshalJSON() ([]byte, error) {
	type wire SandboxCreateRequest
	encoded, err := json.Marshal(wire(r))
	if err != nil || r.presence&presenceDecoded == 0 {
		return encoded, err
	}
	omit := map[string]bool{
		"resourceLimits": r.presence&sandboxCreateResourceLimitsPresent == 0 && r.ResourceLimits == SandboxResourceLimits{},
		"networkPolicy":  r.presence&sandboxCreateNetworkPolicyPresent == 0 && reflect.ValueOf(r.NetworkPolicy).IsZero(),
	}
	return rewriteMembers(encoded, sandboxCreateRequestFieldNames, nil, omit)
}

// UnmarshalJSON decodes into a fresh value and records which struct
// properties were present.
func (r *SandboxCreateRequest) UnmarshalJSON(data []byte) error {
	type wire SandboxCreateRequest
	var decoded wire
	members, err := decodeMembers(data, &decoded)
	if err != nil || members == nil {
		return err
	}
	decoded.presence = presenceDecoded
	if _, ok := members["resourceLimits"]; ok {
		decoded.presence |= sandboxCreateResourceLimitsPresent
	}
	if _, ok := members["networkPolicy"]; ok {
		decoded.presence |= sandboxCreateNetworkPolicyPresent
	}
	*r = SandboxCreateRequest(decoded)
	return nil
}
