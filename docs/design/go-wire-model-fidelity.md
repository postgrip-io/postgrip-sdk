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
checks. TypeScript and Python mappings, contracts, request bytes for existing
callers and signing do not change. Follow [contracts](../development/contracts.md)
and [validation](../development/testing.md).

## Design

### One owner, with checked compatibility declarations

The contract is the owner of every HTTP model. The 59 `go/protocol`
declarations remain the public Go representation of their schemas, because
removing or retyping them would break callers. They are a declared compatibility
mechanism, not an independent model. Today the guides disagree, as described
above. The fidelity-check slice updates both so they state:

- [Contracts](../development/contracts.md): `go/protocol` holds
  runtime-only types plus the compatibility declarations for the
  `GO_PROTOCOL_SCHEMAS` list, which the generator aliases and the fidelity check
  verifies against the contract.
- [Architecture](../development/architecture.md): the same exception, instead
  of a blanket prohibition. No other HTTP model may be declared by hand.

A fidelity check extends the field-name comparison for those schemas. It keeps
bidirectional field-set equality: every schema property has a JSON-tagged Go
field, and every JSON-tagged Go field has a schema property. These schemas are
closed, so an extra serialized field is a mismatch. For every property it then
requires the following of the Go field:

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
  pointer, slice, map, or a value with `omitempty`. For example,
  `PollTaskResponse.Directive *AgentPollDirective` is optional and non-nullable,
  and the pointer is what lets it be absent. A required non-nullable property
  does not use a pointer. A value with `omitempty` encodes a present zero value
  or empty collection as absence; that loss is covered under **Present zero
  values** below, not by this rule.
- For an optional nullable property, an entry in the `go/protocol` presence
  round-trip test table. A property is nullable when its schema allows `null`
  explicitly, or when it references an unconstrained schema such as
  `JsonValue`. A pointer alone also collapses `null` into omission, so
  the check requires every optional nullable property in the contract to appear
  in that table, and the table's tests prove absent, `null` and value round-trip
  unchanged. Removing a type's presence handling then fails its tests, and
  adding a nullable property without an entry fails the check.

The check runs in `check_drift.py` with self-test fixtures for each rule.
Mismatches it finds are corrected in the declarations in the same PR when the
correction keeps the exported field type. Any other mismatch stops that slice
and is raised as a design change; there is no exception list.

Declarations alone do not show the wire shape of the protocol types that
encode through a custom `MarshalJSON` and a shadow struct, such as `Task`,
`TaskEvent` and `AgentSessionResponse`. A Go test therefore encodes a fully
populated value of every such type, and the check compares its emitted keys
with the schema's property set in both directions. A dropped or retagged
shadow field fails it.

### Present zero values

Go maps an optional non-nullable property to a value with `omitempty` by
convention. For 117 such fields across the 59 declarations, the schema accepts
the zero value or an empty collection, which then encodes as absence. Examples
are `TaskResult.ExitCode`, `AgentPollDirective.Force`, `Sandbox.SetupCommand`
and `Sandbox.Labels`. Preserving a present zero value needs either pointer
fields, which changes exported field types across the protocol package, or
presence records on most types. Either is a broad migration with its own
compatibility cost, so this design does not change these fields. It records them
as an open gap for a separate migration design. The fidelity check enforces the
rest of each field's mapping without listing them as exceptions. The guides
state the loss explicitly.

Generating the declarations themselves into `go/protocol` is not part of this
design. It needs a type-override table that reproduces every current exported
field type, and an exported-API comparison that proves the result is identical.
That migration needs its own design.

### Presence for optional nullable properties

The six properties keep their exported field types. Each owning type,
`PollTaskResponse`, `Sandbox` and `TaskResult`, gains an unexported record of
which of its nullable properties were decoded as an explicit `null`, and custom
JSON methods:

- `UnmarshalJSON` first clears the record, then sets it for each property
  present as `null`. A reused value decoded from `{"task":null}` and then from
  `{}` therefore re-encodes as `{}`.
- `MarshalJSON` writes `null` for a property whose field is `nil` and whose
  record is set, and otherwise behaves as today. None of the three types has
  custom JSON methods today.

A value decoded from `{"task":null}` therefore re-encodes as `{"task":null}`. A
value built in code has no record and encodes exactly as today. Equality of two
values can now differ only in that record.

Adding a field, even an unexported one, stops unkeyed composite literals of
these two types from compiling, for example
`protocol.PollTaskResponse{task, directive}`. Keyed literals, field access and
encoding are unaffected. This follows Go's compatibility convention, under which
adding struct fields is compatible and unkeyed literals of another package's
structs may break; `go vet` already reports such literals. The release notes
still name it as a source-compatibility note for the three types.

Custom JSON methods are also promoted to any struct that anonymously embeds one
of these types. For example, marshaling a wrapper that embeds `PollTaskResponse`
and adds its own JSON field would then use the promoted `MarshalJSON` and drop
the wrapper's field. This is a behavior change for such embedding callers. The
release notes name it, and a regression test documents the promoted behavior so
it changes only deliberately.

The generator rejects an optional nullable property in any schema it generates
as a Go struct, rather than mapping it lossily. None exists today, and one that
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
- `protocol.PollTaskResponse`, `protocol.Sandbox` and `protocol.TaskResult`
  keep their exported fields. Decoded values re-encode explicit `null`s, and
  constructed values encode as today when used directly. Unkeyed literals of
  these types stop compiling, and structs that anonymously embed them inherit
  their JSON methods. The release notes record both.
- Present zero values of the 117 optional fields stay lossy, as today, and are
  recorded as an open gap.
- `OpenAPIServiceRuntimeLogWorkerStatus.Settings` and `.Storage` become
  pointers. This is a breaking change to exported field types, and the release
  notes record it.
- Protocol declarations change only where the fidelity check finds a mismatch
  that can be corrected compatibly.

## Delivery slices

1. **Nullable presence.** Add presence handling to `PollTaskResponse`,
   `Sandbox` and `TaskResult` with the round-trip test table, the embedding
   regression test and the generator rejection.
2. **Fidelity check and policy.** Add the check and its self-test, including
   the round-trip table rule, correct any compatible mismatches, and update the
   contracts and architecture guides.
3. **Optional inline objects.** Change the generator, regenerate, and add the
   release note.

Each slice is its own PR under the [review process](../development/contributing.md).

## Acceptance

- Slice 1: round-trip tests cover absent, `null` and value for each of the six
  properties, sequential decoding into one reused value (`null`, then absent),
  and a constructed value encoding as before. A test documents the promoted
  `MarshalJSON` on an embedding struct. A generator fixture with an optional
  nullable property fails generation.
- Slice 2: self-test fixtures prove each fidelity rule fails on a synthetic
  mismatch, including an undeclared extra Go field, an optional nullable
  property missing from the round-trip table, and `json.RawMessage` for a
  closed object. They also prove an optional non-nullable pointer and a raw
  array of `JsonValue` pass. The custom-marshaler wire-shape test fails on a
  shadow struct with a dropped or retagged field. `check_drift.py --monorepo`
  passes on the corrected declarations.
- Slice 3: `ServiceRuntimeLogWorkerStatus` round-trips with `settings` and
  `storage` absent, minimally valid (only their required properties) and fully
  populated. `{}` is not a valid value for either object, because both have
  required properties. Only the Service generated Go
  file changes.
- In every slice, Go tests and vet, generator checks, recorded endpoint and cURL
  runners, and strict documentation builds pass.
