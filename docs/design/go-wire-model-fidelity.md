# Go wire model fidelity

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

OpenAPI owns HTTP models, and language mappings must keep requiredness,
nullability and the difference between an omitted and a null value. The SDK
architecture audit of `main` at `3675b2f2` found two Go gaps:

- **Model ownership (A13).** `scripts/generate_openapi.py:GO_PROTOCOL_SCHEMAS`
  maps 59 Agent schemas to aliases of handwritten `go/protocol` declarations
  instead of generating them. `go/protocol/tools/check_drift.py` checks those
  declarations' JSON field names, not their types, requiredness or
  nullability. The guides also disagree: [contracts](../development/contracts.md)
  says Go Agent declarations alias protocol types, while
  [architecture](../development/architecture.md) says HTTP-owned models are not
  redefined in `go/protocol`. The aliases are a compatibility mechanism, since
  `protocol.Task` and its peers are public. Nothing shows that the mirror bytes
  differ today.
- **Presence (A14).** Two representations lose information:
  - Six optional nullable Agent properties lose an explicit `null`. Five are
    declared nullable: `PollTaskResponse.task` and `Sandbox.expiresAt`,
    `lastActivityAt`, `stoppedAt` and `deletedAt`, each a pointer with
    `omitempty`. The sixth, `TaskResult.value`, references the unconstrained
    `JsonValue` schema, which accepts `null`, and is an `any` with `omitempty`.
    Decoding `{"task":null}` or `{"value":null}` and encoding the result yields
    `{}`.
  - `go_schema_type` ignores optionality for inline objects. The two optional
    inline objects, `ServiceRuntimeLogWorkerStatus.settings` and `storage`,
    become non-pointer structs, so a decoded value without them re-encodes with
    invented zero-valued objects.

  Worker has neither case. These are representation losses in response models,
  not demonstrated changes to server state.

This design covers Go model generation, the protocol declarations and their
checks. TypeScript and Python mappings, contracts and signing do not change.
Request bytes for directly constructed values do not change; the one decoded
request case is described under **Presence handling**. Follow [contracts](../development/contracts.md)
and [validation](../development/testing.md).

## Design

### One owner, with checked compatibility declarations

The contract is the owner of every HTTP model. The 59 `go/protocol`
declarations remain the public Go representation of their schemas, because
removing or retyping them would break callers. They are a declared compatibility
mechanism, not an independent model. Today the guides disagree, as described
above. The first implementation slice updates both, before any declaration
changes, so they state:

- [Contracts](../development/contracts.md): `go/protocol` holds
  runtime-only types plus the compatibility declarations for the
  `GO_PROTOCOL_SCHEMAS` list, which the generator aliases and the fidelity check
  verifies against the contract.
- [Architecture](../development/architecture.md): the same exception, instead
  of a blanket prohibition. No other HTTP model may be declared by hand.

A fidelity check extends the field-name comparison for those schemas. It keeps
bidirectional field-set equality over every field `encoding/json` serializes:
tagged fields, exported untagged fields under their Go names, and fields
promoted from untagged anonymous structs. Every schema property has such a
field, and every such field has a schema property. These schemas are closed, so
an extra serialized field is a mismatch. JSON tag options other than
`omitempty` (for example `,string`) change the encoded type and are rejected.
For every property it then requires the following of the Go field:

- a type compatible with the schema: string, integer, number, boolean,
  date-time, array, map, or a referenced type. `any` is accepted where the
  schema is `JsonValue` or unconstrained. `json.RawMessage` is accepted there
  and also for an array or map of `JsonValue`, because raw JSON represents any
  such value losslessly. This covers the existing `ScheduleAction.Args`,
  `SignalWorkflowRequest.Args` and `SignalWithStartWorkflowRequest.Args`
  fields, which keep their exported type.
- `omitempty` exactly when the property is optional, unless the field is a
  non-pointer value whose zero value the schema rejects.
- For an optional property, a representation that can express absence: a
  pointer, slice, map, or a non-struct value with `omitempty`. `encoding/json`
  never omits a struct value, so an optional struct field (including
  `time.Time`) is absence-capable only through presence handling (see
  **Presence handling**). For example,
  `PollTaskResponse.Directive *AgentPollDirective` is optional and non-nullable,
  and the pointer is what lets it be absent. A required non-nullable property
  does not use a pointer. A value with `omitempty` encodes a present zero value
  or empty collection as absence; that loss is covered under **Present zero
  values** below, not by this rule.
- For an optional nullable property, either `json.RawMessage`, which keeps an
  explicit `null` as the bytes `null`, or an entry in the `go/protocol` presence
  round-trip test table. A property is nullable when its schema allows `null`
  explicitly, or when it references an unconstrained schema such as `JsonValue`.
  `EnqueueTaskRequest.payload` and `Task.payload` are `json.RawMessage`. A
  pointer or interface alone collapses `null` into omission, so the check
  requires every other optional nullable property in the contract to appear in
  that table, and the table's tests prove absent, `null` and value round-trip
  unchanged. Removing a type's presence handling then fails its tests, and
  adding a nullable property without an entry fails the check.

The check runs in `check_drift.py` with self-test fixtures for each rule.
Mismatches it finds are corrected in the declarations in the same PR when the
correction keeps the exported field type. Any other mismatch stops that slice
and is raised as a design change; there is no exception list.

Declarations alone do not show the wire shape of the protocol types that encode
and decode through custom JSON methods and shadow structs, such as `Task`,
`TaskEvent` and `AgentSessionResponse`. A Go test therefore exercises both
directions for every such type, using a fixture that gives each property a
distinct sentinel value of the schema's type, plus a variant with zero-valued
required properties:

- It encodes a value built from the fixture, decodes the emitted JSON
  generically, and compares the property set in both directions along with each
  property's value and JSON type.
- It decodes the fixture payload into the type and compares every exported
  field with its expected value.

A dropped, retagged or misassigned shadow field fails this test, as does a
required property wrongly marked `omitempty`.

### Present zero values

Go maps an optional non-nullable property to a value with `omitempty` by
convention. For 117 such fields across the 59 declarations, the schema accepts
the zero value or an empty collection, which then encodes as absence. Examples
are `TaskResult.ExitCode`, `AgentPollDirective.Force`, `Sandbox.SetupCommand`
and `Sandbox.Labels`. Preserving a present zero value needs either pointer
fields, which changes exported field types across the protocol package, or
presence records on most types. Either is a broad migration with its own
compatibility cost, so this design does not change these fields. It records them
as an open gap for a separate migration design. The same gap records the three
required arrays whose nil slice encodes as `null`, which is invalid for a
required array: `BackfillScheduleResponse.tasks`, `SandboxListResponse.sandboxes`
and `SandboxWorkspaceListResponse.workspaces`. A decoded value keeps a non-nil
empty slice and re-encodes as `[]`; only a value built in code with a nil slice
is affected. The fidelity check enforces the
rest of each field's mapping without listing them as exceptions. The guides
state the loss explicitly.

Generating the declarations themselves into `go/protocol` is not part of this
design. It needs a type-override table that reproduces every current exported
field type, and an exported-API comparison that proves the result is identical.
That migration needs its own design.

### Presence handling

Two groups of properties get presence handling, and all keep their exported
field types:

- the six optional nullable properties above;
- the four optional struct-typed properties that `omitempty` cannot omit:
  `TaskResult.StartedAt` and `FinishedAt` (`time.Time`), and
  `SandboxCreateRequest.ResourceLimits` and `NetworkPolicy`.

Each owning type (`PollTaskResponse`, `Sandbox`, `TaskResult`,
`SandboxCreateRequest`) gains an unexported presence record and custom JSON
methods. The record is a comparable value, a bitmask. `PollTaskResponse` and
`TaskResult` are comparable today and stay comparable and usable as map keys; a
compile-time check guards those two. `Sandbox` and `SandboxCreateRequest`
already contain slices and maps, so they were never comparable. Its bits
are "decoded", one "null" bit per nullable property, and one "present" bit per
struct property.

- `UnmarshalJSON` decodes into a fresh zero value of the type and then replaces
  the receiver, so no field or record bit from an earlier decode survives. It
  sets "decoded", a "null" bit for each nullable property present as `null`,
  and a "present" bit for each struct property present at all.
- `MarshalJSON` writes `null` for a nullable property whose field is `nil` and
  whose "null" bit is set. On a decoded value, it omits a struct property whose
  "present" bit is clear and whose field is still the zero value, so a value
  the caller assigns after decoding is sent. Everything else encodes as today. None of the four
  types has custom JSON methods today.

Presence changes encoding only for decoded values. A value decoded from
`{"task":null}` re-encodes as `{"task":null}`, and a `TaskResult` decoded
without `started_at` no longer re-encodes a year-one timestamp. A value built in
code has no "decoded" bit and encodes exactly as today, including zero-valued
struct properties, so a caller can still send an intentionally zero
`ResourceLimits` or all-false `NetworkPolicy`. A `SandboxCreateRequest` that a
caller builds by decoding JSON (for example from a configuration file) and then
sends is the one request path that changes. If that JSON omits `resourceLimits`
or `networkPolicy`, and the caller leaves them zero, the request now omits
them as well, instead of sending zero-valued objects. That matches the contract, where they are optional, and
the release notes record it. A
constructed value cannot express an absent struct property; that stays part of
the open present-value gap. Equality of two values can now differ only in the
record.

Adding a field, even an unexported one, stops unkeyed composite literals of
these four types from compiling, for example
`protocol.PollTaskResponse{task, directive}`. Keyed literals, field access and
encoding are unaffected. This follows Go's compatibility convention, under which
adding struct fields is compatible and unkeyed literals of another package's
structs may break; `go vet` already reports such literals. The release notes
still name it as a source-compatibility note for the four types.

Custom JSON methods are also promoted to any struct that anonymously embeds one
of these types, in both directions. Marshaling a wrapper that embeds
`PollTaskResponse` and adds its own JSON field uses the promoted `MarshalJSON`
and drops the wrapper's field. Decoding into such a wrapper uses the promoted
`UnmarshalJSON` and leaves the wrapper's field unset. This is a behavior change
for such embedding callers. The release notes name both directions, and
regression tests document them so they change only deliberately.

The generator rejects an optional nullable property in any schema it generates
as a Go struct, rather than mapping it lossily. It resolves component
references and `oneOf`/`anyOf` variants to decide nullability, so a reference to
a nullable component counts, and an unresolvable reference fails generation. None exists today, and one that
appears needs its presence support designed first.

### Optional inline objects

`go_schema_type` returns a pointer for an optional inline object, matching how
it already maps optional referenced objects and scalars. For
`OpenAPIServiceRuntimeLogWorkerStatus`, `Settings` and `Storage` become pointers
to their inline structs, so an absent value decodes as `nil` and re-encodes as
absent.

This changes the exported field types of one generated Service response type.
Reading a field through it still compiles, through Go's automatic dereference,
but panics when the object is absent. Constructing the type with those fields
needs `&`. The release notes record it as a breaking change under the
[release process](../releasing.md).

## Compatibility

- No exported name is removed.
- `protocol.PollTaskResponse`, `protocol.Sandbox`, `protocol.TaskResult` and
  `protocol.SandboxCreateRequest` keep their exported fields and stay
  comparable where they are today. Decoded values re-encode explicit `null`s
  and omit struct properties that were absent. Directly constructed values
  encode as today. A `SandboxCreateRequest` decoded from JSON that omits
  `resourceLimits` or `networkPolicy` now sends them omitted. Unkeyed literals of these types stop compiling, and structs that
  anonymously embed them inherit their JSON methods in both directions. The
  release notes record both.
- Present zero values of the 117 optional fields, and nil encodings of three
  required arrays built in code, stay as today and are recorded as an open gap.
- `OpenAPIServiceRuntimeLogWorkerStatus.Settings` and `.Storage` become
  pointers. This is a breaking change to exported field types, and the release
  notes record it.
- Protocol declarations change only where the fidelity check finds a mismatch
  that can be corrected compatibly.

## Delivery slices

1. **Policy and presence.** Update the contracts and architecture guides to
   the compatibility exception, then add presence handling to
   `PollTaskResponse`, `Sandbox`, `TaskResult` and `SandboxCreateRequest` with
   the round-trip test table, the embedding regression tests and the generator
   rejection.
2. **Fidelity check.** Add the check and its self-test, including the
   round-trip table rule and the custom-JSON wire-shape test, and correct any
   compatible mismatches.
3. **Optional inline objects.** Change the generator, regenerate, and add the
   release note.

Each slice is its own PR under the [review process](../development/contributing.md).

## Acceptance

- Slice 1: round-trip tests cover absent, `null` and value for each of the six
  nullable properties, and absent and present for each of the four struct
  properties. They also cover sequential decoding into one reused value
  (`null` then absent, a value then absent, and a present struct then absent),
  and constructed values encoding exactly as before, including a minimal
  `SandboxCreateRequest`, and a `SandboxCreateRequest` decoded from JSON
  without `resourceLimits` and `networkPolicy` that sends neither, but sends
  them, and an absent `started_at`, once assigned after decoding. A
  compile-time check keeps `PollTaskResponse` and `TaskResult` comparable. Tests document the promoted `MarshalJSON` and
  `UnmarshalJSON` on an embedding struct. A generator fixture with an optional
  nullable property, including one that references a nullable component,
  fails generation.
- Slice 2: self-test fixtures prove each fidelity rule fails on a synthetic
  mismatch, including an undeclared extra tagged Go field, an untagged
  exported field, a field promoted from an untagged anonymous struct, a
  `,string` tag option, an optional nullable
  property missing from the round-trip table, and `json.RawMessage` for a
  closed object. They also prove an optional non-nullable pointer and a raw
  array of `JsonValue` pass, as does `json.RawMessage` for an optional nullable
  `JsonValue`. The custom-JSON wire-shape test fails on a shadow struct with a
  dropped, retagged or misassigned field, in either direction, and on a
  required property wrongly marked `omitempty`. An optional struct field with
  `omitempty` and no presence handling fails the check. `check_drift.py --monorepo`
  passes on the corrected declarations.
- Slice 3: `ServiceRuntimeLogWorkerStatus` round-trips with `settings` and
  `storage` absent, minimally valid (only their required properties) and fully
  populated. `{}` is not a valid value for either object, because both have
  required properties. Only the Service generated Go
  file changes.
- In every slice, Go tests and vet, generator checks, recorded endpoint and cURL
  runners, and strict documentation builds pass.
