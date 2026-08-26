# Phase 2 package-consolidation gate

Status: **PASS**

Completed: 2026-08-25 (America/Los_Angeles)

Reviewer: Codex implementation conformance review

## Revision and contract baseline

- Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`
- Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`
- Coordinated server contract commit:
  `061e3ebc`
- Contract-bundle digest:
  `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`
- Coordinated release version: `0.13.0`

## Scope delivered

- Consolidated the Go SDK into one module while retaining the compatibility
  module path `github.com/postgrip-io/postgrip-agent-sdks/go`.
- Moved the Agent runtime under `go/agent`, Worker management under
  `go/worker`, Service management under `go/service`, and the protocol source
  of truth under `go/protocol`; removed nested modules and `go.work`.
- Consolidated npm publication into `@postgrip/sdk` with root, `./agent`,
  `./worker`, and `./service` export maps.
- Consolidated PyPI publication into `postgrip` with `postgrip.agent`,
  `postgrip.worker`, and `postgrip.service` modules and one root `py.typed`.
- Added Go `Client`, TypeScript `PostGrip`, and Python `PostGrip` plus
  `AsyncPostGrip` root facades. Each resolves one `POSTGRIP_TOKEN` and the
  explicit-plane, plane-environment, common-environment URL precedence.
- Added direct-plane environment constructors without plane-specific token
  variables.
- Added shared URL, token, redirect, and root-configuration mechanics without
  merging plane-owned domain models or operation adapters.
- Added package-boundary, one-token, environment-precedence, packed-artifact,
  wheel-install, and exact-layout checks.
- Updated all known server protocol consumers to import `go/protocol`; their
  complete suites pass against the local unified module. The final remote
  pseudo-version pin is intentionally deferred until the SDK branch is pushed.

## Requirement traceability

| Requirement | Implementation | Test evidence |
| --- | --- | --- |
| Exactly three artifacts | `go/go.mod`, `typescript/package.json`, `python/pyproject.toml`; obsolete roots removed | `scripts/check_package_layout.py` passes |
| Agent is language-scoped | `go/agent`, `typescript/src/agent`, `python/src/postgrip/agent` | layout checker and native import tests |
| One common token | all root facades resolve only `POSTGRIP_TOKEN` and require a non-empty opaque value | request-level tests send the same bearer to all three planes |
| Root and direct clients | root facades plus singular Go/npm/Python planes | compiler tests and installed-artifact smoke tests |
| URL precedence | explicit, `POSTGRIP_<PLANE>_URL`, then `POSTGRIP_URL` | root and direct-plane regression tests in all languages |
| Import isolation | direct planes do not import root facades; management imports do not load Agent/WebSocket code | Go static layout check, TypeScript dependency-graph test, Python subprocess test |
| Shared mechanics | language-internal configuration helpers; Go safe redirect helper | native redirect, URL, token, and configuration tests |
| Protocol cutover | server imports use `github.com/postgrip-io/postgrip-agent-sdks/go/protocol` | shared, host-Agent, and orchestrator suites pass with local module replacement |
| Artifact contents | npm export-map entries and one Python typed marker | npm dry-run content assertion; clean wheel content and install assertions |
| One release version | root `VERSION`, Go `Version`, npm and PyPI metadata | layout checker reports `0.13.0` in all ecosystems |

## Commands and summarized results

- `cd go && GOWORK=off go test ./... && go vet ./...`: passed all unified
  Go packages.
- `cd typescript && bun install --frozen-lockfile && bun run typecheck && bun
  run build && bun run test`: passed 110 tests.
- npm dry-run packing: all eight runtime/declaration export files present;
  127 files, 152,565 bytes.
- `cd python && PYTHONPATH=src python3 -m unittest discover -s test`: passed
  119 tests with one opt-in live-server skip.
- clean Python wheel: 35 files, only `postgrip/`, and exactly one `py.typed`;
  installation into a fresh environment with dependencies and all root/direct
  imports passed.
- all three generator drift checks, operation inventory, package layout, and
  protocol drift self-test plus monorepo check: passed.
- coordinated server checks using temporary module replacements:
  `postgrip-shared`, `postgrip-agent`, and `postgrip-agentorchestrator` all
  passed their complete Go suites against `go/protocol`.

## Deviations and corrective actions

The first TypeScript test run exposed old HTTP fixtures that did not opt into
the newly shared insecure-development control. The fixtures now set that
control explicitly, and all HTTPS enforcement plus native tests pass.

The first Python wheel dry run retained an obsolete `postgrip_agent` tree from
a pre-move build directory. The build output was removed, the wheel was rebuilt
from a clean tree, and a content assertion now rejects all three obsolete
module prefixes.

After the protocol move, the drift checker initially scanned `go/protocol` as
if it were an SDK mirror and its GitHub fallback self-test still expected the
old path. The checker now excludes the source-of-truth directory from the
alias audit, tests the new path, and passes both self-test and monorepo modes.

The package audit found duplicated URL/token validation and safe-redirect
setup in the Go management clients. These mechanics moved to
`go/internal/transport`; TypeScript and Python received equivalent private
configuration modules. Plane-specific request behavior remains in each plane
adapter as required by the design.

No unresolved Phase 2 deviations remain.

## Remaining risks

- The coordinated server modules use a local replacement until the SDK branch
  is pushed. Phase 5 pins the resulting remote pseudo-version and reruns the
  same server suites without local replacements.
- Registry ownership and coordinated server deployment remain the release
  risks recorded in Phase 0; no package publication is attempted by this work.
