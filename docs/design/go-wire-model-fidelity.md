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
  - The five optional nullable Agent properties, `PollTaskResponse.task` and
    `Sandbox.expiresAt`, `lastActivityAt`, `stoppedAt` and `deletedAt`, use a
    pointer with `omitempty`. Decoding `{"task":null}` and encoding the result
    yields `{}`.
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
mechanism, not an independent model. Both guides state this:

- [Contracts](../development/contracts.md) states that `go/protocol` holds
  runtime-only types plus the compatibility declarations for the
  `GO_PROTOCOL_SCHEMAS` list, which the generator aliases and the fidelity check
  verifies against the contract.
- [Architecture](../development/architecture.md) states the same exception
  instead of a blanket prohibition. No other HTTP model may be declared by hand.

A fidelity check replaces the field-name comparison for those schemas. For
every property it requires the following of the Go field:

- the same JSON name;
- a type compatible with the schema: string, integer, number, boolean,
  date-time, array, map, a referenced type, or `any`/`json.RawMessage` only
  where the schema is `JsonValue` or unconstrained;
- `omitempty` exactly when the property is optional, unless the field is a
  non-pointer value whose zero value the schema rejects;
- a pointer, slice or map exactly when the property is optional and nullable,
  or presence-aware.

The check runs in `check_drift.py` with self-test fixtures for each rule.
Mismatches it finds are corrected in the declarations in the same PR when the
correction keeps the exported field type. Any other mismatch stops that slice
and is raised as a design change; there is no exception list.

Generating the declarations themselves into `go/protocol` is not part of this
design. It needs a type-override table that reproduces every current exported
field type, and an exported-API comparison that proves the result is identical.
That migration needs its own design.

### Presence for optional nullable properties

The five properties keep their exported pointer fields. Each owning type,
`PollTaskResponse` and `Sandbox`, gains an unexported record of which of its
nullable properties were decoded as an explicit `null`, and custom JSON methods:

- `UnmarshalJSON` sets the record for a property present as `null`.
- `MarshalJSON` writes `null` for a property whose field is `nil` and whose
  record is set, and otherwise behaves as today.

A value decoded from `{"task":null}` therefore re-encodes as `{"task":null}`. A
value built in code has no record and encodes exactly as today. Equality of two
values can now differ only in that record.

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
- `protocol.PollTaskResponse` and `protocol.Sandbox` keep their exported fields.
  Decoded values re-encode explicit `null`s, and constructed values encode as
  today.
- `OpenAPIServiceRuntimeLogWorkerStatus.Settings` and `.Storage` become
  pointers. This is the only breaking change, and the release notes record it.
- Protocol declarations change only where the fidelity check finds a mismatch
  that can be corrected compatibly.

## Delivery slices

1. **Fidelity check and policy.** Add the check and its self-test, correct any
   compatible mismatches, and update the contracts and architecture guides.
2. **Nullable presence.** Add presence handling to `PollTaskResponse` and
   `Sandbox`, plus the generator rejection.
3. **Optional inline objects.** Change the generator, regenerate, and add the
   release note.

Each slice is its own PR under the [review process](../development/contributing.md).

## Acceptance

- Slice 1: self-test fixtures prove each fidelity rule fails on a synthetic
  mismatch. `check_drift.py --monorepo` passes on the corrected declarations.
- Slice 2: round-trip tests cover absent, `null` and value for each of the five
  properties, and a constructed value encodes as before. A generator fixture
  with an optional nullable property fails generation.
- Slice 3: `ServiceRuntimeLogWorkerStatus` round-trips with `settings` and
  `storage` absent, present-empty and populated. Only the Service generated Go
  file changes.
- In every slice, Go tests and vet, generator checks, recorded endpoint and cURL
  runners, and strict documentation builds pass.
