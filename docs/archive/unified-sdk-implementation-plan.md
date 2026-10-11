> Historical record. Original status, findings and validation below describe
> the recorded revision, not current policy or current release clearance. See
> [current owners](../index.md) and [release gates](../releasing.md).

# Unified PostGrip SDK Implementation Plan

Status: Active — Phase 0 passed on 2026-08-25

This plan implements the decisions in
[Unified PostGrip SDK Design](unified-sdk-design.md). The design is normative
for public behavior and security boundaries. This document owns sequencing,
source moves, test infrastructure, documentation generation, and release
cutover.

## Workstreams

The cutover has five coordinated workstreams:

1. Server authentication and contract standardization.
2. Contract generation and detailed API documentation.
3. Go, TypeScript, and Python package consolidation.
4. Exhaustive endpoint, cURL, and protocol testing.
5. CI, documentation hosting, and coordinated release automation.

The unified SDK must not ship before the server workstream is deployed.
Packaging one credential into three current clients does not create a common
authorization model.

## Gated development model

Development occurs on one SDK feature branch, using phase-scoped commits. No
SDK pull request is opened until all six phase gates and the final integration
gate pass.

The next phase may begin only when the current phase report has status `PASS`.
If the implementation deviates from the normative design or this plan, work
stops at the current gate and follows the corrective loop below. There are no
silent waivers.

### Phase gate procedure

At the end of every phase:

1. Freeze the phase scope and record the design revision, server contract
   commits, and contract-bundle digest used for the work.
2. Run the phase-specific checks plus all cumulative regression checks from
   earlier phases.
3. Compare the code, generated output, package contents, documentation, and
   tests with every applicable normative design requirement.
4. Update the design traceability matrix with the implementing files and test
   evidence for each requirement.
5. Record every deviation and classify it as an implementation defect, a
   missing design decision, or a newly discovered constraint.
6. Complete the corrective action, rerun the affected checks, and repeat the
   conformance review.
7. Mark the gate `PASS` only when all required evidence is present and there
   are zero unresolved deviations.

A gate with missing evidence is `BLOCKED`, not provisionally passed. Later
work must not be used to conceal or defer a failed earlier gate.

### Corrective loop

An implementation defect is corrected in code and tests without changing the
design. A missing or infeasible design decision is handled by updating and
reviewing the design first, then correcting the implementation. An intentional
change in direction is not an exception: it becomes a documented design
revision and all affected earlier gates are rerun.

Corrective work stays in the current phase. If a later phase exposes a prior
phase defect, reopen the earliest affected gate, correct it, rerun that gate
and every dependent cumulative check, then resume the later phase.

### Phase reports

Commit one report per gate under:

```text
docs/unified-sdk-phase-reports/
  phase-0-server.md
  phase-1-generation.md
  phase-2-packages.md
  phase-3-documentation.md
  phase-4-endpoints.md
  phase-5-release.md
  final-integration.md
```

Each report contains:

```text
status
design and plan revision
server contract commits and contract-bundle digest
phase scope and delivered files
requirement -> implementation -> test evidence matrix
commands run and summarized results
artifact and coverage reports
deviations found
corrective actions completed
remaining risks (not unresolved deviations)
reviewer and completion date
```

Reports contain no credentials, customer data, or unredacted live test output.

### Gate criteria

| Gate | Required evidence before continuing |
| --- | --- |
| Phase 0 | Registry name availability and ownership are recorded; server contracts implement common auth, operation classes, standardized errors, Agent bootstrap, and global-admin separation; disposable server environment passes auth tests; protocol consumers are inventoried |
| Phase 1 | Generation is deterministic; every operation is represented; annotation schemas and drift checks pass; no duplicate generated trees exist |
| Phase 2 | Exactly three installable artifacts build; root and direct imports work; import boundaries and full native tests pass; protocol consumers build against the new path |
| Phase 3 | Every operation has digest-matched reference documentation; secure cURL examples pass recorded conformance; documentation links and examples are drift-free |
| Phase 4 | Every public operation has recorded test ownership; cURL or protocol coverage has zero unexplained gaps; required disposable and isolated live suites pass |
| Phase 5 | Three release workflows pass dry runs; version and digest match across artifacts; obsolete release paths are gone; artifact contents and size reports pass |

### Final integration gate

After Phase 5, run the complete validation from a clean checkout and clean
tool caches. Recheck every design acceptance criterion, every phase report,
the final source tree, installed artifacts, detailed documentation, recorded
operation coverage, and required live suites.

The final gate passes only when:

- every phase report is `PASS` at the final design revision;
- the traceability matrix covers every acceptance criterion;
- no unresolved deviation, stale compatibility path, or unexplained operation
  exception remains;
- the coordinated server contract commits are fixed and tested;
- the full CI-equivalent command set passes from a clean checkout;
- the proposed PR diff contains only the reviewed unified-SDK work.

Only then is the SDK pull request opened. The PR includes links to the design,
implementation plan, all gate reports, generated coverage report, test results,
and the coordinated server change.

### Coordinated server repository

The canonical server contracts live in a different repository, so one SDK PR
cannot contain the Phase 0 server implementation. Server work is developed on
a coordinated server branch and deployed to an isolated integration
environment for the SDK phase gates.

At final integration, either the server change is already merged and deployed,
or a linked server PR and the SDK PR are opened together. Merge order is server
first and SDK second; the unified SDK is not released until the server change
is deployed. The commitment to one end-of-work PR applies to this SDK
repository and does not hide the required cross-repository change.

## Repository target

```text
contracts/
  agent-openapi.json
  worker-openapi.json
  service-openapi.json

go/
  go.mod
  client.go
  agent/
  worker/
  service/
  protocol/
  internal/

typescript/
  package.json
  src/
    client.ts
    agent/
    worker/
    service/
    internal/
  test/

python/
  pyproject.toml
  src/postgrip/
    __init__.py
    client.py
    agent/
    worker/
    service/
    _internal/
  test/

docs/
  api/
  unified-sdk-design.md
  unified-sdk-implementation-plan.md
  unified-sdk-phase-reports/

scripts/
test/
  operation-tests.json
  operation-notes.json
```

## Source mapping

Use `git mv` so file history remains inspectable.

| Current path | Target path | Purpose |
| --- | --- | --- |
| `go/client/` | `go/agent/client/` | Agent application client |
| `go/activity/` | `go/agent/activity/` | Workflow activities |
| `go/workflow/` | `go/agent/workflow/` | Workflow runtime |
| `go/worker/` | `go/agent/worker/` | Agent runtime worker |
| `go/failure/` | `go/agent/failure/` | Agent failures |
| `go/internal/` | `go/agent/internal/` or `go/internal/` | Agent-only or shared internals |
| `go/workerclient/` | `go/worker/` | Worker management |
| `go/serviceclient/` | `go/service/` | Service management |
| `protocol/` | `go/protocol/` | Runtime wire contract in unified Go module |
| `typescript/src/` | `typescript/src/agent/` | Existing Agent implementation except root facade |
| `typescript-worker/src/` | `typescript/src/worker/` | Worker management |
| `typescript-service/src/` | `typescript/src/service/` | Service management |
| `python/src/postgrip_agent/` | `python/src/postgrip/agent/` | Agent namespace |
| `python-worker/src/postgrip_worker/` | `python/src/postgrip/worker/` | Worker namespace |
| `python-service/src/postgrip_service/` | `python/src/postgrip/service/` | Service namespace |
| `openapi.json` | `contracts/agent-openapi.json` | Agent contract mirror |
| `worker-openapi.json` | `contracts/worker-openapi.json` | Worker contract mirror |
| `service-openapi.json` | `contracts/service-openapi.json` | Service contract mirror |

The top-level `worker` namespace means Worker management. The Agent runtime
worker remains below `agent/worker` in every language.

## Phase 0: server prerequisites

The coordinated server change must be implemented, contract-tested, and
deployed to an isolated integration environment before SDK consolidation
continues. It must be merged and deployed to production before the unified SDK
PR merges or any unified artifact is published.

Before source work begins, verify `@postgrip/sdk` on npm and `postgrip` on PyPI
and record the registry owners responsible for them. Both registry metadata
endpoints returned `404 Not Found` on 2026-08-25. Reservation requires an
authorized registry identity and is therefore a pre-merge release-owner gate,
not a source-development mutation. The final PR must remain blocked from merge
and release until the PostGrip organization supplies reservation evidence for
both names; package publication is never performed merely to make a phase
report pass.

### Common tenant token

- Define one tenant-bound management security scheme for Agent, Worker, and
  Service management operations.
- Issue URL-safe printable-ASCII token values without whitespace, quotes,
  backslashes, or control characters.
- Permit a token to carry concrete grants from multiple planes.
- Add a complete Agent management scope matrix.
- Preserve server-side tenant derivation and reject tenant overrides in request
  data.
- Use stable authentication and authorization error codes.
- Serve the three deployed public contracts from predictable OpenAPI URLs.

### Operation classification

Classify every route as one of:

- public;
- tenant API;
- delegated Agent runtime;
- global administration.

Record accepted credentials separately from the operation class. Selected
Agent tenant-API operations continue to accept either the common management
token or a delegated Agent session; the server applies management scopes to the
former and Agent namespace, queue, lease, and capability claims to the latter.

Move global-administration operations out of the public Agent SDK contract and
into a separately owned internal server-administration contract. The three
public SDK contracts contain no operation that requires a global-admin token.

### HTTP behavior

Standardize the public contracts on an error envelope containing `code`,
`message`, `requestId`, and optional structured `details`. Document status
codes, idempotency, ETags, preview tokens, bounded retries, `Retry-After`, and
streaming behavior as operation metadata.

This does not require renaming every established request or response field.
Plane-specific pagination and wire naming remain generated from their owning
contracts.

### Agent runtime bootstrap

The first unified release supports host injection only. A host-managed runtime
receives:

```text
POSTGRIP_AGENT_ID
POSTGRIP_AGENT_ACCESS_TOKEN
POSTGRIP_AGENT_REFRESH_TOKEN
POSTGRIP_AGENT_ACCESS_EXPIRES_AT
POSTGRIP_AGENT_SIGNING_PRIVATE_KEY
```

The SDK loads and refreshes these values internally. There is no management
token exchange endpoint in this release. Local processes without host-injected
credentials cannot call delegated runtime routes.

### Protocol consumers

Before moving `protocol/`, inventory every repository and service importing
the current module. Update the orchestrator verifier, host Agent runtime, and
any other consumers to the unified Go module path. Preserve wire bytes, JSON
names, and `agent-task-v1` signing exactly.

The server import migration and SDK protocol move land as one coordinated
cutover. Do not stop the old protocol release until every known consumer builds
against the new location.

## Phase 1: generation and metadata

Update `scripts/generate_openapi.py` so plane and language select the target
output directory. Generated output includes operation IDs, routes, auth class,
required scopes, safety classification, idempotency, pagination, content
types, request/response schemas, and contract digest.

Generated code must not import the root facade. The dependency direction is:

```text
root facade -> plane client -> shared internal transport
                         \-> plane generated contract
```

Run generation into the target layout and remove the old generated files in
the same change. Never retain two writable generated trees.

### Operation inventory and annotations

Generation produces an immutable operation inventory from OpenAPI. It contains
only derivable facts:

```text
operation ID, plane, method, path, schemas, auth class, scopes,
safety class, accepted credentials, protocol class, idempotency, pagination,
contract digest
```

Checked-in sidecars own human decisions:

- `test/operation-tests.json` records fixtures, cleanup, mock test, live test,
  cURL eligibility, and approved protocol exception.
- `test/operation-notes.json` records behavioral documentation keyed by stable
  operation ID.

Both sidecars have closed JSON schemas. CI fails on unknown operation IDs,
duplicate keys, missing required ownership, stale entries, or exceptions
without a reason and owner.

## Phase 2: package consolidation

### Go

- Retain only `go/go.mod`.
- Move the protocol, Worker, and Service packages into that module.
- Remove nested `go.mod` files after imports are updated.
- Simplify or remove `go.work` when only one module remains.
- Add a root `postgrip.Client` facade with `Agent`, `Workers`, and `Services`.
- Keep direct plane package imports supported within the same module.
- Run tests both normally and with `GOWORK=off` during the transition.

### TypeScript

- Retain one publishable `typescript/package.json` and lockfile.
- Export the root facade and singular subpaths `./agent`, `./worker`, and
  `./service` with `types` and `default` conditions.
- Add package-content tests for every exported JavaScript and declaration file.
- Ensure importing one subpath does not evaluate another plane or load optional
  WebSocket code.

### Python

- Retain one `python/pyproject.toml` and one `postgrip` package.
- Expose singular modules `postgrip.agent`, `postgrip.worker`, and
  `postgrip.service`.
- Add `PostGrip` and `AsyncPostGrip` root facades.
- Retain one `py.typed` marker.
- Build and install the wheel before testing imports and all three facades.

### Root facade

The root facade resolves URLs and `POSTGRIP_TOKEN`, constructs each plane
client, and exposes them through stable properties. It delegates operations and
does not duplicate generated methods or models.

Plane clients remain directly testable and must not import the root facade.
Import-boundary tests enforce this rule.

### Shared transport

Extract only mechanics shared by all planes:

- URL normalization and HTTPS enforcement;
- bearer injection and cross-origin redirect protection;
- cancellation and bounded response reads;
- structured error decoding;
- bounded retry and `Retry-After` parsing;
- idempotency-key validation;
- cursor/page iteration primitives;
- JSON encoding and content-type validation;
- request ID propagation and user-agent construction.

Contract-specific limits, field names, routes, and domain models remain with
their plane. Do not unify similar wire types without a canonical contract
change.

### Handwritten client split

Split large handwritten files behind the new namespaces:

```text
agent:   tasks, workflows, schedules, sandboxes, runtime
worker:  inventory, jobs, logs, operations
service: inventory, deployments, runtime, logs, administration
```

Keep generated low-level clients separate from ergonomic facades. Isolate
archive, streaming, signing, and WebSocket adapters from ordinary JSON
operations.

## Phase 3: detailed API documentation and cURL

Add `scripts/generate_api_docs.py`. It renders:

- a plane and resource index;
- one detailed page per operation;
- parameter and schema tables;
- request, response, and error examples;
- required scopes and credential class;
- safety, idempotency, retry, pagination, and lifecycle notes;
- secure cURL plus Go, TypeScript, and Python examples;
- the exact contract digest.

`--check` renders into a temporary directory and compares output without
modifying the worktree.

### Secure cURL template

Generated examples pass the bearer header through a cURL configuration on
standard input, not a process argument:

```sh
curl --config - \
  --fail-with-body --silent --show-error \
  "${POSTGRIP_URL}/api/v1/workers" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

Examples require cURL 7.76 or newer for `--fail-with-body`. They prohibit shell
tracing and never contain literal credentials. The test runner passes live
credentials to cURL over standard input, redacts subprocess output, and never
adds the expanded bearer value to argv.

Body examples use inline non-secret JSON or protected temporary files. If
standard input is needed for the request body, the runner uses a mode-0600
temporary cURL config and removes it in a `finally` path.

### Versioned publication

Generation computes one contract-bundle digest over all three public specs.
The documentation pipeline publishes an immutable reference at:

```text
/reference/<contract-bundle-digest>/
```

`/reference/latest/` redirects to the newest deployed bundle. Every SDK embeds
the digest and links to its immutable reference. A release never links to
documentation generated from an unreleased `main` contract.

## Phase 4: exhaustive endpoint tests

Add these root scripts:

```sh
python3 scripts/generate_api_docs.py --check
python3 scripts/check_operation_coverage.py
python3 scripts/test_api_endpoints.py --plane all
python3 scripts/test_curl_examples.py --plane all
```

### Pull-request gate

Every pull request runs:

- contract and generated-output drift checks;
- operation inventory and annotation validation;
- detailed documentation generation checks;
- all native unit, type, vet, build, and coverage suites;
- recorded HTTP conformance for every operation in every language client;
- a real cURL process for every cURL-eligible management operation;
- dedicated recorded protocol tests for archive, streaming, WebSocket, and
  signed Agent runtime operations.

The recording server validates method, path, query, headers, body bytes,
authentication class, idempotency metadata, and response decoding. It returns
schema-valid fixtures and performs no real mutation.

### Nightly disposable integration

Nightly CI runs tenant API operations against an environment marked as
disposable. The fixture manager creates uniquely prefixed resources, records
every identifier, and cleans up in reverse dependency order.

Destructive operations require both the disposable-environment marker and an
explicit flag. Cleanup uses explicit recorded identifiers, never wildcards. A
cleanup failure reports remaining identifiers without hiding the original
failure.

### Pre-release protocol integration

Before release, isolated jobs exercise:

- delegated Agent polling, refresh, and signed mutations with a real host
  runtime fixture;
- archive upload and download;
- continuous logs and cancellation;
- sandbox WebSocket sessions;
- destructive Service lifecycle and administration operations.

Global administration is tested in the server repository because it is not in
the public SDK contracts.

### Production smoke tests

Production smoke tests use an explicit allowlist of public health and read-only
operations. They never perform mutation, runtime control, secret writes,
deletion, or global administration.

### Coverage report

CI publishes JSON and Markdown reports with:

```text
operations | documented | SDK-generated | cURL | protocol exceptions |
recorded-tested | nightly-owned | pre-release-owned | production-smoke-owned
```

Expected counts are derived from OpenAPI. The gate requires every operation to
have documentation, generated-client ownership, recorded coverage, and either
cURL or a justified protocol runner. Approved exceptions are visible and never
counted as cURL coverage.

Static reports count live-tier ownership, never execution. Each live workflow
publishes a cleanup ledger containing the exact contract digest, operation
results, resource IDs, cleanup status, and remaining IDs. Only a successful
workflow run plus that ledger is `nightly-live` or `pre-release-live` evidence.

## Phase 5: CI and release cutover

Replace plane-specific builds and releases with one validation and publishing
path per ecosystem:

```text
publish-go
publish-typescript
publish-python
```

All three distributions use one root `VERSION` and release the same SemVer.
Release tags remain ecosystem-prefixed:

```text
go/vX.Y.Z
typescript/vX.Y.Z
python/vX.Y.Z
```

Each workflow verifies the tag and shared version, runs all contract and
recorded gates, builds the artifact, installs or unpacks it, exercises all
public namespaces, verifies the embedded contract digest, and publishes only
after every check succeeds.

Record artifact sizes, dependency changes, build time, and installed smoke
time. Unexpected material growth requires explicit release approval.

## Landing sequence

1. Update repository guidance, including `AGENTS.md`.
2. Implement and contract-test the server prerequisites, then deploy them to an
   isolated integration environment.
3. Inventory and migrate protocol consumers.
4. Add the generated operation inventory and checked-in annotation schemas.
5. Update generation, drift, documentation, and cURL tooling.
6. Consolidate the Go module and restore all Go checks.
7. Consolidate TypeScript and validate the packed npm artifact.
8. Consolidate Python and validate the installed wheel.
9. Add root facades and common environment configuration.
10. Split oversized handwritten clients behind the new namespaces.
11. Add recorded, nightly, pre-release, and production-safe test tiers.
12. Consolidate CI, documentation hosting, and release workflows.
13. Remove obsolete package roots, manifests, token variables, and workflows.
14. Pass the final integration gate and open the linked end-of-work PR or PRs.

If intermediate commits cannot remain publishable, keep them on one feature
branch and merge only after the repository passes. Never publish a mixed state
where one language documents unified authentication while another still
requires plane-specific credentials.

No SDK PR is opened during these steps. Phase reports and corrective commits
remain on the feature branch until the final integration gate passes.

## Completion checklist

- Server common-token and standardized-error changes are deployed.
- Global administration is absent from all public SDK contracts.
- Every known protocol consumer uses the unified Go module path.
- Exactly three SDK artifacts are published.
- All three artifacts carry the same version and contract-bundle digest.
- Root and direct plane imports work in every language.
- `POSTGRIP_TOKEN` authenticates all three tenant API planes according
  to its grants.
- Host-injected Agent runtime credentials refresh and sign correctly.
- Every public operation has generated documentation and recorded coverage.
- Every eligible management operation has a tested secure cURL example.
- Nightly and pre-release live suites pass in disposable environments.
- Package contents, artifact size, dependency inventory, and documentation
  links are verified before publication.
- All phase reports and the final integration report are `PASS` against the
  final design revision with zero unresolved deviations.
