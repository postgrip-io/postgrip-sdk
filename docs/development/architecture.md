# SDK architecture and responsibility rules

## Required MVC-ish pattern

Use the same responsibility separation as
[web's MVC-ish architecture](https://github.com/postgrip-io/postgrip-web/blob/main/code-review/architecture.md):
pure models, explicit orchestration, external adapters and a composition root.
These rules apply to new and changed code in every SDK language, including
small features. Plane clients and runtime orchestration take the controller or
application-service role. SDKs have no rendering layer; a public facade is a
composition root, not a View. Do not add UI controllers, database repositories or empty
pass-through layers solely to imitate web's directory structure.

| SDK role | Responsibility | Boundary |
| --- | --- | --- |
| Models and contracts | Generated OpenAPI HTTP types and operation metadata; runtime protocol types; pure validation and transformations | No network calls, credential loading, mutable runtime state or concrete client dependencies. |
| Plane clients and runtime orchestration | Idiomatic operations and multi-step SDK behavior; managed execution, polling and lifecycle coordination | Consume typed operations and focused adapter interfaces; keep HTTP mechanics and server-side business/authorization policy out. |
| Generated operation bindings | Map typed arguments to the contract's operation, path, query, headers and body | Delegate execution; no handwritten retry, refresh, signing or application workflows. |
| Transport and protocol adapters | HTTP execution, serialization, error decoding and protocol-specific signing, refresh exchange, archive or WebSocket framing | Implement the contract and the owning runtime's policy; do not choose application workflows or depend on the root facade. |
| Root facade / composition | Resolve configuration and construct Agent, Worker and Service clients with the appropriate dependencies | No request loops, wire-model definitions or plane business logic; direct plane imports stay usable. |

Keep the dependency direction explicit: facades compose clients; clients and
runtime orchestration consume contracts and adapter interfaces; concrete
adapters implement those interfaces. Models depend on neither clients nor
adapters. Shared transport imports no plane, and planes must not depend on
another plane or the root facade. Put focused interfaces at the consuming
boundary or in a neutral contract module, and wire implementations at composition.
Generated bindings should depend on an executor contract rather than a concrete
runtime adapter. This is a dependency rule, not a prescribed class hierarchy.

Every language layers HTTP execution the same way: generated plane modules,
shared transport, runtime adapters, plane clients, then the root facade.

- Generated plane modules hold schema types, the operation table and thin
  typed operation functions. They import only the standard library and the
  shared transport's operation types.
- Shared transport owns the one executor, retry policy, base error type and
  cursor paging. It imports no plane, runtime adapter or root facade.
- Runtime adapters (signing, session refresh, long polling, WebSocket relay,
  archive streams, log followers) wrap the executor through hooks and never
  re-implement request execution.
- Plane clients build idiomatic methods from generated operations, runtime
  adapters and shared transport.
- The root facade composes planes and passes common configuration to each.

Planes never import the root facade or another plane. Plane differences, such
as error type and text, retry ceilings, redirect policy and response bounds,
are executor configuration rather than copies of the request loop.

Group code by plane/capability, then separate responsibilities within it. A
handwritten module owns one role and responsibility; split when ownership
demands it, not at an arbitrary line count. Generated contract modules may
colocate schemas and mechanical operation bindings, but must not contain
handwritten execution policy. Share genuinely neutral mechanisms in internal
infrastructure while keeping plane-specific policy explicit. Preserve public
imports with compatibility exports when extracting internals. Do not introduce
new cycles, copy legacy mixed responsibilities, or weaken checks to permit them.

## OpenAPI and language mapping

[Contracts](contracts.md) owns canonical web specifications, byte-for-byte SDK
mirrors, generation and cross-repository validation. HTTP methods, paths,
operation IDs, schema requiredness/nullability, enums, headers, status handling
and `x-postgrip-*` policy annotations must survive each language's mapping.
Idiomatic naming and sync/async APIs may differ; wire meaning must not. Model
open-ended data only where the schema permits it. Runtime-only types retain
their separate protocol owner; do not redefine HTTP-owned models there.

| Language | Apply the roles idiomatically |
| --- | --- |
| Go | Root `go/client.go` composes planes. Agent HTTP clients live in `go/agent/client/`, management clients in `go/worker/` and `go/service/`, protocol types in `go/protocol/`, and shared HTTP infrastructure in `go/internal/transport/`. Use focused interfaces and packages, generated structs with exact JSON tags, `context.Context` for cancellation, and compatible typed errors. Preserve the published module path. |
| TypeScript | `typescript/src/client.ts` composes planes; `src/{agent,worker,service}/` own their clients and generated bindings; `src/internal/` owns shared infrastructure. Use typed interfaces/functions, explicit named ESM exports and deliberate package subpaths. Keep request cancellation in adapters and preserve the contract's distinction between omitted and null values. |
| Python | `python/src/postgrip/client.py` composes planes; the three plane packages own clients and generated bindings; `_internal/` owns shared infrastructure. Use focused typed modules and consumer-facing protocols where needed, deliberate package exports, and compatible exceptions. Sync/async wrappers share execution policy; preserve cancellation, omitted/null distinctions and per-invocation state. |

There are currently three supported languages. A fourth language needs its own
design mapping these same roles and all three public planes, plus generator,
wire/protocol parity, package/export, validation and release integration. Add
its checks and artifact ownership with the implementation; do not create a
language-specific wire contract or imply support before those gates exist.

## Current implementation and enforcement limits

The boundaries above are requirements for new and changed code, not a claim
that all existing code has been migrated. The
[contract-driven layering design](../design/contract-driven-sdk-layering.md)
delivers executor decoupling and transport consolidation in slices. Go's
generated operation tables emit `transport.Operation` values, and Go Worker
and Go Service run their operations through the shared executor in
`go/internal/transport`. Other planes are not yet moved: Go's generated Agent
client still holds a concrete `Connection`, and TypeScript and Python still
duplicate transport policy in plane clients.
The design's remaining timeout, retry and error changes stay proposed until
delivered and reflected in current behavior guides; an architectural extraction
must preserve existing plane behavior unless its design explicitly includes a
behavior change.

`scripts/check_package_layout.py` checks artifact layout, selected exports,
selected plane-to-root imports and the absence of TypeScript wildcard
re-exports; `--self-test` proves the wildcard rule against generic fixtures.
`typescript/test/public-surface.test.ts` records each TypeScript entry's
published names. Neither enforces the layering rule above, plane-to-plane or
transport-to-plane imports, or responsibility ownership. Generator and drift checks likewise do not prove
runtime compatibility. Use the responsibility review below and the actual
[validation checks](testing.md); web's architecture linters and size ratchets
are not installed SDK enforcement.

## Package boundaries

`go/`, `typescript/` and `python/` each publish one artifact with Agent, Worker
management and Service management namespaces. Root facades configure these
clients; direct plane imports remain usable independently. Generated clients
must not depend on the root facade. Shared transport helpers belong in the
language's internal infrastructure and must preserve each plane's policy.

Wire ownership and compatibility are defined in [contracts](contracts.md).
Authentication and endpoint configuration are owned by [authentication](../authentication.md)
and [configuration](../configuration.md). Never route a common management token
to a delegated runtime or public refresh endpoint.

## Runtime responsibilities

Agent clients submit or inspect tasks, workflows and schedules. A host-launched
managed runtime owns polling, leases, refresh, signing and workflow/activity
execution. SDKs do not enroll standalone host agents. Worker management is a
separate namespace; an Agent polling worker is not a Worker-management client.

Go's `agent/workflow.Context` is the customer interface; its implementation
belongs in `agent/worker`. Keep replay infrastructure independent of SDK failure
types and translate replay cancellation/determinism errors at the worker boundary.
Workflow suspension blocks the task; it must not become a task failure.
Activity runtime context is per invocation, never global.

Language-specific runtime semantics and examples have one owner each:

- [Go runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/go/agent/docs/workflow-runtime.md)
  and [package responsibilities](https://github.com/postgrip-io/postgrip-sdk/blob/main/go/agent/docs/packages.md).
- [TypeScript runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/typescript/docs/workflow-runtime.md).
- [Python runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/python/docs/workflow-runtime.md).

Preserve deterministic replay, continuation/cancellation semantics and public
exports when refactoring. Sandbox checks are limited static checks, not an
isolation guarantee. No removal of a published API based only on absent local
callers. JSON conversion and signing changes need compatibility evidence.

## Style and public surface

Use `gofmt`, idiomatic exported Go comments, two-space TypeScript with explicit
named exports, and four-space Python following PEP 8. Keep TypeScript ESM
subpaths and Python exports deliberate. Do not add another artifact for an
existing language or a plane-specific release path. Adding a supported language
requires the design and integration above; [releasing](../releasing.md) owns
tags and version coordination.

## Responsibility review

Review the implementation against its cited design and the roles above. Design
drift and boundary violations are findings with the same standing as bugs;
passing generation, type checks or tests does not establish correct ownership.

- Trace a public call through its client, generated operation and adapter.
  Verify where orchestration, wire mapping and I/O occur, including same-module
  calls that import checks cannot see. Models stay pure and facades only compose.
- Verify OpenAPI conformance in every affected language, including optional vs
  null values, error/status handling, auth lanes, idempotency and retry policy.
  Reject handwritten competing schemas and edits to generated output without
  corresponding generator/contract changes.
- Check management, delegated-runtime and public credential separation at the
  adapter boundary. Review signing bytes and runtime consumers explicitly;
  field-name drift checks alone are insufficient.
- Preserve direct plane imports, public exports and error compatibility. Check
  cancellation, deadlines, redirects, response limits, cursor behavior and
  replay/suspension semantics when their owning paths change. Shared code must
  retain required differences between planes and languages.
- Require observable regression evidence for changed behavior at the public
  SDK boundary, plus focused model/adapter checks where needed. Do not accept
  silent skips, weakened assertions or recorded transports as live evidence.
- Check affected current guides and coordinated web changes. Reject a split
  that leaves mixed responsibilities, an exception that hides a breach, or a
  claim of checker coverage or language support the repository does not provide.

## Historical decisions

See the [historical SDK records](../archive/index.md) for the unification design,
phase evidence and dated simplification review. Current requirements are above;
old results do not establish present release readiness.
