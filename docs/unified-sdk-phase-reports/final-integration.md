# Final integration gate

Status: **PASS**

Completed: 2026-08-26

Reviewer: Codex implementation conformance review

Design SHA-256: `c381af949ea5da1378462c1a130d8fb43742e6cd3ab7fd246111210e8471aa6a`

Implementation-plan SHA-256: `e548a76a725210f116fe0663df40b421c4260d4a9a8c7cd35c6c5730d429e32e`

Contract-bundle SHA-256: `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`

## Coordinated revisions

- SDK branch: `postgrip-io/postgrip-sdks`, `feat/unified-sdk`
- SDK module revision consumed by the server:
  `c61a4bf40f536801e62cb085882feaebdb3d3120`
- Coordinated server common-auth/contracts commit:
  `be2b080161b58d9a294b6c5b144a8a188c162779`
- Coordinated server final commit:
  `a81fc23940882767e0cb76673e8047499c27f175`
- Server module dependency:
  `github.com/postgrip-io/postgrip-agent-sdks/go@v0.12.4-0.20260826075702-c61a4bf40f53`

The host Agent, Agent Orchestrator, and shared sandbox module resolve that
published branch revision directly. None uses a local SDK replacement or the
former standalone protocol module.

## Acceptance traceability

| Design acceptance criterion | Final implementation and evidence |
| --- | --- |
| One artifact per language | Exactly `go/go.mod`, `typescript/package.json`, and `python/pyproject.toml`; package-layout and release checks pass |
| Same coordinated version | Root, Go, npm, and PyPI metadata are all 0.13.0 |
| Same contract bundle | All nine language/plane bindings embed `b728fee5…` |
| Singular plane namespaces | Go `/agent`, `/worker`, `/service`; npm `/agent`, `/worker`, `/service`; Python `.agent`, `.worker`, `.service`; clean-install smokes pass |
| One developer management token | Root clients load `POSTGRIP_TOKEN`; 390 recorded language-operation checks validate management credential class |
| Runtime auth remains delegated | Session refresh, access token, and Ed25519 signing remain host-injected; five signed operations per language verify canonical bytes |
| Global administration is server-only | Public inventories contain 130 tenant/public operations and reject global-admin classification |
| Standard public errors and scopes | Coordinated server route/contract tests and disposable PostgreSQL common-token integration pass |
| Unified protocol ownership | Protocol is `go/protocol`; three server consumers build/test from the exact unified module pseudo-version |
| Detailed immutable docs | 130 digest-matched operation pages pass generation and static validation |
| AI-agent-friendly cURL | 121 eligible operations execute a real cURL process with bearer material absent from argv; nine protocol exceptions remain explicit |
| Exhaustive SDK endpoint tests | 130 operations × three languages = 390 strict recorded checks, plus native archive, signing, polling, refresh, and WebSocket adapters |
| Live test policy | Every operation owns a nightly, pre-release, or production-safe tier; destructive/external runs require disposable or protected infrastructure |
| Three release paths | Only `publish-go`, `publish-typescript`, and `publish-python`; all call reusable full validation and protected owner/deployment gates |

## Phase gate results

| Phase | Report | Result |
| --- | --- | --- |
| 0 | Server common authentication and contracts | PASS |
| 1 | Deterministic generation and inventory | PASS |
| 2 | Language package consolidation | PASS |
| 3 | Detailed API documentation and secure cURL | PASS |
| 4 | Exhaustive endpoint tests and coverage | PASS |
| 5 | Unified CI and publishing cutover | PASS |

Each phase compared its implementation to the design and recorded corrective
actions before work continued. The final upstream merge added Worker signer
visibility; the contract already contained those fields, generated files were
regenerated, the upstream regression tests were migrated to the common `pgt_`
token, and all final suites passed. The first linked-server PR run then exposed
stale Agent API reference assertions and coverage prose for the removed public
global-admin operation. The server reference, consolidated install examples,
coverage counts, and regression tests were corrected in `4b2f2aa8`; its Agent
reference suite now passes all 110 tests. The next server run exposed a legacy
JSON-import seam in the new delegated-session columns: nil Go slices encoded as
SQL `NULL` for non-null scope arrays. The persistence adapter now normalizes
legacy bindings to concrete empty arrays, with a focused unit regression; the
exact PostgreSQL 16 migration and Agent store integration lane passes.
An unrelated Worker progress test then revealed that it waited for completion
but asserted an independently asynchronous progress callback immediately. Its
gate now waits for both observable outcomes; the focused race ran 100 times and
the complete Worker test and vet suites pass.

## Final evidence

- Go: 14 packages pass `GOWORK=off go test ./...` and `go vet ./...`; all
  seven package coverage floors pass.
- TypeScript: frozen install, typecheck, build, 112 native tests, coverage,
  pack inspection, and clean installed-subpath smoke pass.
- Python: wheel build, 121 native tests with one opt-in external live skip,
  85% aggregate coverage, wheel inspection, and clean installed-submodule
  smoke pass.
- Contracts and docs: runtime drift (67 total types), all 130 generated HTTP
  operations, 130 fixtures, 130 reference pages, and 121 cURL examples pass.
- Recorded transport: 390 SDK requests validate route, query, header, body,
  auth lane, signing bytes, protocol ownership, and response decoding.
- Artifacts: Go 102 files / 828,110 bytes; npm 127 files / 147,887 packed
  bytes; Python 35 files / 87,583 bytes. All remain below reviewed limits.
- Coordinated server: shared, host Agent, and Agent Orchestrator full test and
  vet suites pass without an SDK replacement.
- Workflow syntax: `actionlint` 1.7.7 passes every GitHub workflow.
- Documentation: root, TypeScript, and Python strict builds pass.
- Whitespace and generation drift checks pass.

## External release controls

Opening the linked PRs does not publish a package. Release tags remain blocked
by protected environments until the server change is merged and deployed and
authenticated npm/PyPI owners record control of the designed registry names.
Those are explicit publication approvals; there is no repository code
deviation hidden behind them.

No unresolved source, package-layout, authentication, documentation, endpoint
coverage, CI, or release-automation deviation remains for merge review.
