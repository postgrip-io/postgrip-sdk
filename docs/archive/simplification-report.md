> Historical record. Original status, findings and validation below describe
> the recorded revision, not current policy or current release clearance. See
> [current owners](../index.md) and [release gates](../releasing.md).

# Validated Repository Simplification Report

**Validated:** 2026-08-27
**Branch:** `feat/zero-touch-platform-automation`
**Commit reviewed:** `981f630`
**Change scope:** tracked repository validation plus the behavior-preserving mechanical refactors listed below. Public API removals, wire changes, retry-policy changes, and generated output changes were deferred.

## Executive summary

The original report had a sound central observation: the largest maintainability cost in the tracked repository is repeated transport, pagination, replay, and generator plumbing. It was not valid as written, however, because it counted an untracked local directory as three repository package groups and occasionally treated “no in-repository caller” as proof that a published SDK API was dead.

This revision uses Git-tracked files as the repository boundary. It excludes generated files from refactor targets, except where the proposed change belongs in the generator. It also separates three materially different kinds of work:

- **Mechanical candidate:** private duplication or dead private code; behavior should remain unchanged.
- **Behavior decision:** similar implementations already differ, so maintainers must choose and test the intended policy before sharing code.
- **API/wire decision:** exported methods, fields, wire types, generated surface, or release automation; local usage searches cannot establish whether removal is compatible.

The strongest recommendations are:

1. Share small, policy-neutral Worker/Service transport primitives in Go, Python, and TypeScript. Consolidate the full retry/request loops only after their intentional behavior differences are documented.
2. Remove the structurally redundant Go protocol JSON methods only after adding golden wire tests and correcting the inaccurate timestamp-normalization documentation. Removing the methods changes the exported method set even if `encoding/json` output remains the same.
3. Consolidate query/update execution and milestone construction inside each Agent runtime. These are private duplication, but replay-sensitive paths deserve regression tests.
4. Resolve Go fields that are accepted but ignored. Deprecate, reject, or implement them through a coordinated public API change; do not silently delete them.
5. Create a small shared contracts/tooling module for stable helpers such as plane metadata, bundle digests, and casing. Preserve the stricter reference-resolution semantics required by the generator.

## Execution status

This change implements the recommendations that could be made mechanically while preserving the public SDK and wire contracts:

- **Go:** shared internal pager and log-follower state machines (G5), removed the duplicate Worker idempotency context channel (G6), and made `WaitForTaskCompletion` the implementation rather than a wrapper (part of G7).
- **Python:** shared HTTP test fakes, replay handler execution, milestone construction, sync/async pagination, idempotency validation, agent-ID/name normalization, and direct Python 3.11 timestamp parsing; simplified workflow search conversion; removed the two confirmed private dead declarations (P2–P8, P10–P11, with P7 limited to the unambiguous helpers).
- **TypeScript:** shared replay handler execution, log following, cancellable delay, milestone construction, and terminal-task classification; removed confirmed package-private dead exports; added the named `WorkflowInfo` return type and simplified `PostGrip.fromEnv` (T2, T4–T5, T7, T9–T10).
- **Tooling:** shared plane/digest/casing helpers, hoisted repeated OpenAPI inventory and row computation, shared the recording-server lifecycle, removed `shell_json`, and removed the recorded-only `--mode` option and its documented invocations (S1–S2, S5, S9–S10, limited to the behavior-preserving portions).

The report's behavior, API/wire, release-automation, and optional style decisions remain recommendations rather than changes. In particular, the plane-specific request/retry loops, protocol JSON method sets, ignored public fields, mirror-type ownership, schema policy, and workflow consolidation were not changed. Generated OpenAPI bindings and reference pages remain byte-for-byte current according to their check modes.

## Scope and validation corrections

### Repository boundary

At the start of the review, `postgrip-agent-sdks/` contained **zero tracked files** in this checkout. It was an untracked local tree, as were coverage output and extra generated-reference directories. The original sections 4–6 contained 44 findings against that local tree, and original finding 7.1 counted the same tree again. Those 45 findings are removed from this repository audit.

Untracked workspace cleanup is an index/worktree hygiene decision, not a source-code simplification finding. It should be performed only after separating intended new source files from disposable local artifacts.

### What was validated

The retained observations were checked against tracked source, tests, public export files, package manifests, the OpenAPI generator, and CI workflow references. The following contract checks passed during validation:

```text
python3 go/protocol/tools/check_drift.py --self-test
python3 go/protocol/tools/check_drift.py --monorepo

check_drift self-test OK.
Drift check OK (59 protocol-backed OpenAPI and 8 runtime-only types verified).
```

That drift check proves the currently configured mirrors agree. It does not prove that a proposed refactor is behavior-preserving.

After implementation, Go tests (both workspace and `GOWORK=off`) and `go vet` passed; TypeScript type checking, build, and 129 tests passed; and Python's 132 discovered unit tests passed with one skip. The all-plane OpenAPI generation check, API documentation generation, operation coverage, 432 recorded SDK endpoint ownership checks, 135 recorded cURL conformance checks, and all three release-artifact inspections also passed. The standalone documented `python -m pip wheel` command could not be invoked because this environment has no `python` executable, but `check_release_artifacts.py --ecosystem all` successfully built and inspected the Python artifact.

### Material corrections to the original report

- The Go protocol contains about 336 lines of custom JSON methods across six types, not approximately 700 lines across two repository protocol packages. The second package was in the untracked local tree.
- `AgentEnrollmentKey` and `AgentAuthSession` have no production consumers in this repository, but they do have JSON-shape tests in `go/protocol/types_test.go`. “Zero references including tests” was incorrect.
- `ActivityTaskPayload` is explicitly protected by `TRACKED_TYPES` in `check_drift.py`. `AgentUpgradeRequest` is mirrored in all three languages but is **not** in that list and was not found in the Agent OpenAPI contract. The two types must not be described as having identical drift protection.
- TypeScript’s `ActivityTaskPayload` and `AgentUpgradeRequest` declarations are exported from `types.ts`; they are omitted from the public `agent/index.ts` barrel. Calling them simply “unexported” was imprecise.
- Service retry options whose defaults equal their maximums are still meaningful because callers can lower the limits. The issue is constrained and asymmetric configuration, not “vacuous” configuration.
- The guarded `AbortSignal.any`/`AbortSignal.timeout` fallback is compatibility behavior, not dead code. Removing it saves little and narrows runtime support, so it is not recommended here.
- Public APIs such as `ScopedClient`, `Connection.request`, and `fromEnv` are not dead merely because this repository has no callers. They should be retained unless deprecation is justified using published compatibility requirements and consumer evidence.

## Go SDK

### G1. Worker and Service transport code shares structure but not one policy

**Disposition: behavior decision.**

`go/worker/client.go:120-262` and `go/service/client.go:165-322` repeat request construction, bounded response reads, error decoding, retry-status checks, jitter, waiting, and idempotency handling. The differences are observable:

- Service carries arbitrary generated headers; Worker forwards only the idempotency key.
- Service has configurable retry limits and distinguishes a present zero `Retry-After`; Worker uses fixed limits and does not preserve that distinction.
- Service handles an overflowing numeric `Retry-After`; Worker’s `strconv.Atoi` path does not.

Treat these as policy differences until proven otherwise. A safe first step is to share pure primitives—visible-ASCII idempotency validation, bounded body reading, retryable-status classification, and cancellable waiting—while leaving plane-specific request policy in each client. Extract a whole shared loop only after table-driven tests define parity and intended differences.

### G2. Six protocol JSON method pairs are structurally redundant

**Disposition: API/wire decision.**

`go/protocol/types.go` defines custom `MarshalJSON` and `UnmarshalJSON` methods for `Task`, `AgentEvent`, `EnrollAgentRequest`, `AgentSessionResponse`, `AgentEnrollmentKey`, and `AgentAuthSession`. Each method copies fields to or from a shadow struct with the same order, types, and JSON tags. No normalization is performed.

`go/protocol/CLAUDE.md` nevertheless says `Task.UnmarshalJSON` tolerates legacy epoch-second timestamps. The implementation uses `time.Time` directly and does not do that. Before removing the methods:

1. confirm whether legacy timestamp support is required by the runtime;
2. add golden tests for field names, omission behavior, timestamp forms, and representative output bytes;
3. update the documentation to match the chosen behavior; and
4. account for the fact that direct calls to these exported methods would no longer compile.

### G3. Several public workflow options are accepted but ignored

**Disposition: API/wire decision.**

`go/agent/workflow/workflow.go:65-84` exposes `ActivityOptions.StartToCloseMs`, `HeartbeatTimeoutMs`, and `CancellationType`, plus `ChildWorkflowOptions.CancellationType` and `CancellationScope`. The execution path at `go/agent/worker/workflow_context.go:235-259` reads only task queue, lease timeout, and retry fields for activities; repository-wide searches found no reader for the listed fields.

Choose one outcome per field: implement it in the protocol, reject non-zero values with a clear error, or deprecate it for a later breaking release. Documentation alone should not imply that an ignored option works.

### G4. `SignalWithStartOptions.SignalName` is redundant and ignored

**Disposition: API decision.**

`go/agent/client/inputs.go:103-107` exposes `SignalName`, while `WorkflowClient.SignalWithStart` takes the authoritative signal name as a positional argument and uses only that argument at `workflow_client.go:92-105`. Setting the option field does not override the positional value. Deprecate the field or redesign the signature in a breaking release; do not describe the current behavior as always sending an empty name.

### G5. Pagers and log followers repeat the same state machines

**Disposition: mechanical candidate.**

The five exported pager implementations in `go/service/pager.go` and `go/worker/pager.go`, and the three log iterators in `go/service/logs.go` and `go/worker/logs.go`, have small repeated cores. Generic internal state machines can sit behind the existing exported wrapper types. Preserve the Service-specific `PollAfterMs` behavior and all current method signatures.

### G6. Worker idempotency data travels through two context channels

**Disposition: mechanical candidate.**

Every mutating Worker call first stores the key through `withIdempotencyKey` and then supplies the same key through generated headers. `doOpenAPI` reads the first value and overwrites it when generated headers are present. Keep one header path and retain validation as a plain helper. Add a retry test proving the key still enables retries for mutations.

### G7. Small private helpers can be consolidated

**Disposition: mechanical candidate.**

- `transport.FirstNonEmpty`, `orDefault`, and `firstNonEmpty` overlap, but trimming behavior differs. Name the semantics explicitly rather than replacing calls mechanically.
- `WaitForTaskCompletion` is a one-line exported wrapper over `waitForTaskCompletion`; make the exported function the implementation and update the two internal callers.
- `go/agent/client/json.go` and `go/agent/worker/helpers.go` contain thin renames of `jsonenv` helpers. Direct calls would reduce indirection, though the line-count benefit is small.

### G8. Agent client forwarding has three layers in several paths

**Disposition: API decision.**

Sandbox and schedule operations commonly flow through subclient → exported `Connection` method → generated OpenAPI client. Some middle methods add only pointer conversion, while other connection methods contain authentication or transport behavior. Inventory the methods by behavior before removing a layer. Because `Connection` methods are public and mirror other SDKs, this is release-level API work rather than a routine internal cleanup.

### G9. Service administration wrappers are generator-shaped

**Disposition: generator/API decision.**

`go/service/administration.go` repeats validate-and-delegate wrappers for many operations. Generation could reduce maintenance, but the output would remain public API and must retain comments, signatures, and error behavior. If pursued, change `scripts/generate_openapi.py`, never the generated files, and require byte-for-byte or intentionally reviewed output diffs.

### G10. Protocol types lack production consumers in this repository

**Disposition: API/wire decision.**

`CompactRequest`, `CompactResponse`, `StoreStats`, `AgentEnrollmentKey`, and `AgentAuthSession` were not found in tracked production code outside their declarations. The latter two are exercised by JSON-shape tests. This is evidence for an ownership review, not proof of dead public API: `go/protocol` is imported by the external runtime according to its package documentation. Confirm out-of-repository consumers before removal.

### G11. Example dotenv loaders are byte-identical

**Disposition: optional mechanical candidate.**

`go/agent/example/greeting/env.go` and `go/agent/example/longrun/env.go` are byte-identical 50-line files. A shared `example/internal` package removes duplication, but keeping examples independently copyable may be more valuable. Treat this as an explicit style choice, not urgent debt.

## Python SDK

### P1. Worker and Service duplicate transport infrastructure

**Disposition: behavior decision.**

`python/src/postgrip/worker/client.py` and `python/src/postgrip/service/client.py` repeat cancellation-aware connection classes, redirect control, request/retry loops, response decoding, `Retry-After` parsing, jitter, and async thread bridging. Their behavior is not identical: Service has configurable limits and finite-value handling that Worker lacks, and cancellation plumbing differs in some followers.

As in Go, first extract policy-neutral helpers into `_internal`. Define the plane-specific policy through explicit parameters and tests before moving the complete request loop.

### P2. Test HTTP fakes are triplicated

**Disposition: mechanical candidate.**

`python/test/test_root_client.py`, `python/test/service/test_client.py`, and `python/test/worker/test_client.py` each define `FakeResponse`/`FakeOpener`-style support with small behavioral differences. Move a deliberately feature-complete version under `python/test/` and keep test-specific behavior explicit.

### P3. Query and update execution duplicate one replay flow

**Disposition: mechanical candidate with replay-sensitive tests.**

`python/src/postgrip/agent/agent.py:165-229` repeats validation, history fetch, replay, handler invocation, and completion. A private helper parameterized by task kind can preserve public behavior. Tests should cover missing handlers, replay blocking, handler failures, and completion payloads for both kinds.

### P4. Milestone formatting is duplicated

**Disposition: mechanical candidate.**

`agent/workflow.py` and `agent/activity.py` repeat event-detail and message construction. Keep their public runtime-specific functions separate, as required by package guidance, and share only the pure builder.

### P5. Pagination loops repeat across sync/async and resource types

**Disposition: mechanical candidate.**

There are eight analogous cursor loops in the Service and Worker clients. Shared sync and async iterator helpers can preserve the current public methods. Parameterize the response cursor key (`nextCursor` versus `nextPageToken`) rather than hiding it in conditionals.

### P6. Timestamp parsing can use Python 3.11 behavior

**Disposition: mechanical candidate after focused tests.**

`agent/client.py:1053-1080` manually rewrites `Z` and truncates fractional seconds. The package requires Python 3.11+, whose `datetime.fromisoformat` accepts `Z` and longer fractional components and normalizes to microseconds. Replace the preprocessing only after tests cover `Z`, explicit offsets, naive values, invalid input, and fractions longer than six digits.

### P7. Small normalization helpers repeat

**Disposition: mechanical candidate.**

- Six connection methods repeat `agent_id or worker_id`; centralize the resolution and preserve the current `TypeError` text.
- Several methods repeat enum-or-string name normalization.
- `_duration_ms` in `agent/client.py` and `_duration_ms_nullable` in `agent/agent.py` are equivalent. The separate `_duration_ms` in `workflow.py` converts seconds to milliseconds and should be renamed, not merged blindly.

### P8. Idempotency-key validation appears at five call sites

**Disposition: mechanical candidate.**

Move the repeated visible-ASCII regular expression and error construction to `_internal/config.py`. Tests should prove identical acceptance and error messages for both planes.

### P9. Facade construction and environment factories contain smaller duplication

**Disposition: mechanical candidate; keep public factories.**

`PostGrip` and `AsyncPostGrip` repeat configuration resolution and Agent construction, differing mainly in the Worker/Service client classes. Their own `from_env` methods are direct constructor aliases. The plane-specific `from_env` methods are different: they explicitly read the supplied environment mapping. Share their bodies where useful, but retain public factory names for cross-language consistency unless separately deprecated.

### P10. Query-option conversion does avoidable flatten/unflatten work

**Disposition: mechanical candidate with query golden tests.**

`_generated_workflow_query` reconstructs `search_attributes` immediately after `_query_options` flattened them. Build the generated query directly for this path. Verify exact query keys and omission behavior before changing wire-adjacent code.

### P11. Confirmed private dead code

**Disposition: mechanical candidate.**

- `T = TypeVar("T")` in `worker/client.py` has no use.
- `encode_public_key` in `agent/_signing.py` has no tracked caller and is not part of the public Agent export list.

Delete these with the normal package checks. Do not infer the same status for public `Connection.request`; it may intentionally be a raw-request escape hatch.

### P12. Administration attribute assignment is repetitive but type-sensitive

**Disposition: optional mechanical candidate.**

The sync and async `ServiceAdministration` constructors assign many annotated groups individually. A data-driven `setattr` loop is shorter, but explicit assignments are friendly to static analysis and navigation. Make this change only if type checking and generated documentation stay equally clear.

### P13. `ServiceReference` validates at multiple boundaries

**Disposition: API behavior decision.**

Moving validation to `__post_init__` would centralize the invariant, but it changes when hand-built invalid references fail. That is observable behavior. Prefer removing only the provably redundant `for_service` validation call, or treat constructor validation as an intentional compatibility change with tests.

## TypeScript SDK

### T1. Worker and Service repeat transport code

**Disposition: behavior decision.**

`typescript/src/worker/client.ts` and `typescript/src/service/client.ts` repeat request/retry loops, error decoding, query encoding, idempotency checks, `Retry-After`, jitter, and abortable delay. Public error classes must remain distinct, and Service retry configuration differs from Worker policy. Start with pure internal helpers; consolidate full control flow only after behavior tables and tests exist.

### T2. Query and update execution duplicate replay configuration

**Disposition: mechanical candidate with replay-sensitive tests.**

`agent/agent.ts:270-400` contains near-parallel query and update paths, including repeated runtime configuration. A private discriminated helper can reduce drift. Preserve task-specific payload keys, handler maps, event labels, and error codes in tests.

### T3. Hand-built query encoding overlaps generated encoders

**Disposition: wire-adjacent mechanical candidate.**

All three generated plane modules export `encodeOpenAPIQuery`, while hand-written Agent, Worker, and Service paths still construct query strings locally. Reuse each plane’s generated helper where its typed operation model fits. First add golden tests for arrays, nullish values, `search.*` maps, and the Worker `signal` omission; equivalence should not be assumed from similar names.

### T4. Log following and delay helpers repeat

**Disposition: mechanical candidate.**

Three polling generators have the same loop shape, and multiple delay implementations differ mainly in abort semantics. Share a follower core and explicitly named delay variants such as resolve-on-abort, reject-on-abort, and uninterruptible delay. Do not merge semantically different cancellation behavior into one ambiguous helper.

### T5. Confirmed package-private dead exports

**Disposition: mechanical candidate.**

`nextRetryDelayMs` and `generateSigningKey` are exported from their source modules but have no tracked caller and are not re-exported through the public Agent barrel. Remove them unless direct source-module imports are intentionally supported (the package export map does not expose those modules).

### T6. Two apparently unused mirror types have different protection

**Disposition: API/wire decision.**

`ActivityTaskPayload` and `AgentUpgradeRequest` have no tracked production consumer and are omitted from `agent/index.ts`. Both are mirrored in Go, TypeScript, and Python, but only `ActivityTaskPayload` is explicitly in `check_drift.py:TRACKED_TYPES`. For `AgentUpgradeRequest`, either remove all three declarations after confirming external protocol consumers, or add it to the drift contract if it remains required.

### T7. Milestone construction and terminal-error classification repeat

**Disposition: mechanical candidate.**

Workflow and activity milestone entry points must remain distinct, but their pure message/details builder can be shared. Likewise, the repeated terminal-task error-message predicate should have one auditable definition. Preserve exact emitted objects and matching rules in tests.

### T8. Service mutation helpers encode policy indirectly

**Disposition: mechanical candidate.**

`ServiceClient.mutate` uses a hand-maintained `Exclude` union, and `administrationMutation` uses a Boolean to select conditional validation. Replace the Boolean with named helpers or an explicit options object. Ensure the type system still prevents read operations from entering mutation paths.

### T9. `workflowInfo()` has an opaque public return type

**Disposition: API-compatible type cleanup.**

The 11-key `Omit` resolves to four returned fields. A named `WorkflowInfo` interface improves declarations and prevents accidental widening. Keep it structurally identical and verify the emitted `.d.ts`.

### T10. `PostGrip.fromEnv` has unnecessarily complex typing

**Disposition: API-compatible type cleanup.**

Its parameter type is structurally `PostGripConfig`, and the constructor already resolves the environment. Simplify the type and body while keeping the public factory for consistency. Unlike this root factory, Worker and Service factories explicitly read `process.env` or a supplied mapping.

### T11. Keep the signing module behind its dynamic-import boundary

**Disposition: retain current design.**

`connection.ts` reconstructs `AgentSigningKey` through `Awaited<ReturnType<...>>` because the package-boundary test rejects even a type-only static dependency on `_signing.ts`. Keep that indirection unless the boundary test and emitted dependency graph are deliberately redesigned. The original suggestion to replace browser-safe byte codecs wholesale with global `Buffer` is not retained; it offers little value and changes portability assumptions.

The `AbortSignal.any`/`timeout` compatibility guards are also retained. The package documents Node 20+ but contains browser-aware sandbox paths, and removing a working fallback is not a meaningful simplification.

## Scripts, tests, and repository automation

All 12 tracked Python entry points under `scripts/` have repository references in CI, other scripts, or documented workflows. There is no dead-script finding.

### S1. Stable contract helpers are duplicated

**Disposition: mechanical candidate with digest tests.**

Plane constants, bundle digest framing, and casing helpers appear in multiple scripts. Move the stable common subset to `scripts/_contracts.py`. `generate_openapi.resolve_ref` and `generate_api_docs.resolve` are not drop-in equivalents: the former follows chained local references and rejects unsupported references, while the latter resolves one level and tolerates values it cannot resolve. Align their contracts deliberately before sharing a resolver.

### S2. OpenAPI generation repeats plane dispatch and work

**Disposition: generator refactor.**

`generated_files()` has three plane branches that vary mostly by paths, package names, prefixes, and extra Service outputs. A plane descriptor can drive one emitter. In addition, `operation_inventory_source()` reloads and validates all contracts once per selected plane, and `main()` recomputes operation rows for counts. Hoist those computations. Require `python3 scripts/generate_openapi.py --plane all --check` and review output diffs.

### S3. API documentation checks overlap

**Disposition: owner decision.**

`check_api_docs.py`, `check_operation_coverage.py`, and `check_operation_inventory.py` repeat some page-existence, marker, and inventory-key checks. Some duplication may be intentional defense in depth. Document which checker owns each invariant before consolidating; do not remove independent security checks merely for line count.

### S4. Checked-in JSON Schemas are not the primary validators

**Disposition: behavior decision.**

`operation-fixture.schema.json` and `live-scenario.schema.json` are not applied directly by the corresponding runners, and the operation inventory/test/note schemas are meta-checked while Python code performs the instance validation. Since CI already installs `jsonschema`, apply schemas where they cover the same constraints and retain Python checks for cross-file or operation-specific invariants that JSON Schema cannot express.

### S5. Recording HTTP server harnesses repeat

**Disposition: mechanical candidate.**

`test_api_endpoints.py` and `test_curl_examples.py` implement similar `ThreadingHTTPServer` lifecycle, method routing, URL, and shutdown support. Extract a small shared test-server helper while keeping their different recording models explicit.

### S6. Package/version invariants have several owners

**Disposition: release-automation decision.**

`check_package_layout.py`, `check_release_artifacts.py`, and CI shell commands overlap on package names, versions, and module layout. Centralizing the cheap static assertions in `check_package_layout.py` would make the policy easier to review; artifact inspection should remain in `check_release_artifacts.py`.

### S7. Generator signature construction repeats

**Disposition: mechanical generator candidate.**

Python implementation signatures and Protocol stub signatures are assembled separately in `generate_openapi.py`. A shared structured signature description can prevent drift. Keep rendering separate where syntax differs, and use `--check` to prove unchanged generated output.

### S8. Go query/header emitters overlap

**Disposition: mechanical generator candidate.**

`go_query_struct` and `go_header_struct` share field and encoding construction, and two array branches currently emit the same code. Extract only the common representation; retain separate renderers if that keeps generated code clearer.

### S9. `shell_json` is dead

**Disposition: mechanical candidate.**

`scripts/generate_api_docs.py:219-220` has no tracked caller. Delete it.

### S10. Recorded-only `--mode` flags removed

**Disposition: coordinated CLI cleanup.**

`test_api_endpoints.py` and `test_curl_examples.py` previously accepted `--mode` with only `recorded` as a valid value. The redundant flag and its CI/docs uses were removed. The separate `--validate-only` flags remain useful manual/CI interfaces and are not classified as dead solely from sparse references.

### S11. Live workflows repeat setup

**Disposition: release-automation decision.**

The three live workflows repeat environment plumbing, package installation, drift self-tests, and ledger upload. A reusable workflow or composite action could centralize this, but secret flow, permissions, environments, and failure behavior must remain visible and separately reviewable.

### S12. `createWorker` documentation policy is distributed

**Disposition: security-sensitive design decision.**

The crash-safe bootstrap example is special-cased in the docs generator, checker, and cURL runner. A typed per-operation override descriptor could centralize those exceptions. Preserve the current safety markers and add self-tests for the descriptor; this is not a blind string-deduplication task.

## Remaining remediation sequence

1. **Focused residual mechanical work:** the trimming-sensitive helper portion of G7, T8, and the unimplemented generator portions of S2 and S7–S8. Require focused equivalence tests.
2. **Transport extraction:** G1, P1, and T1. Begin with policy-neutral primitives; consolidate control flow only after documenting plane differences.
3. **Wire-adjacent equivalence work:** T3 and S4. Add golden tests first.
4. **Public API and protocol decisions:** G2–G4 and G8–G10, P13, T6, and S6 and S12. Batch breaking changes into a deliberate release.
5. **Optional/style decisions:** G11, P9 and P12, and S3 and S11. Pursue only where the navigation or maintenance benefit is clear.

## Validation gates for implementation work

Run the checks relevant to each change and the complete set before merging a cross-language simplification:

```sh
cd go && go test ./... && GOWORK=off go test ./... && go vet ./...
cd typescript && bun run typecheck && bun run build && bun run test
cd python && python -m pip wheel --no-deps . -w /tmp/wheel \
  && PYTHONPATH=src python -m unittest discover -s test
python3 go/protocol/tools/check_drift.py --self-test
python3 go/protocol/tools/check_drift.py --monorepo
python3 scripts/generate_openapi.py --plane all --check
python3 scripts/generate_api_docs.py --check
python3 scripts/check_operation_coverage.py
python3 scripts/test_api_endpoints.py --plane all
python3 scripts/test_curl_examples.py --plane all
python3 scripts/check_release_artifacts.py --ecosystem all
```

For a mechanical refactor, “tests pass” is necessary but not sufficient. Generated output, wire bytes, request query strings, retry/cancellation behavior, and published declarations should either remain identical or have an explicitly reviewed compatibility change.
