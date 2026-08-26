# Final integration gate

Status: **BLOCKED — external live execution evidence required**

Updated: 2026-08-26

Reviewer: Codex implementation conformance review

Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`

Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`

Contract-bundle SHA-256: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`

## Coordinated revisions

- SDK repository/branch: `postgrip-io/postgrip-sdks`, `feat/unified-sdk`
- Server repository/branch: `sungkim11/postgrip-web`,
  `feat/unified-sdk-auth`
- Server common-auth baseline: `be2b080161b58d9a294b6c5b144a8a188c162779`
- Server history-pagination correction:
  `061e3ebc413108d9cec024cf14196ac4979ab2eb`
- Server authentication and consumer correction:
  `ecf0cd151fd6c380c612d091a5b2a1370ce6df15`
- Server administration-boundary correction:
  `0bdcb756a31a70cce7596c783beff2282f5d752a`
- Server SDK-boundary and Agent-recovery correction:
  `c0fbb3b7951cd010fc33e16bf294862ee20544ec`
- SDK transport and live-target correction:
  `db1c7827643fb40c008573343635f093dbc7b69f`
- SDK final fixture and raw-HTTP correction:
  `9e35ddf2a4fbe68ec8cb3f73f6f01bb96576da14`

The Agent contract is byte-identical between those branches. All nine
language/plane generated surfaces embed the current bundle digest.

## Acceptance traceability

| Design acceptance criterion | Current implementation and evidence |
| --- | --- |
| One artifact per language | Exactly `go/go.mod`, `typescript/package.json`, and `python/pyproject.toml`; layout and artifact checks pass |
| Same coordinated version | Root, Go, npm, and PyPI metadata are 0.13.0 |
| Same contract bundle | All nine bindings embed `5b44c873…` |
| Singular namespaces | Go `/agent`, `/worker`, `/service`; npm subpaths; Python submodules; installed-package smokes pass |
| One developer management token | Root clients load `POSTGRIP_TOKEN`; recorded auth-lane checks use one token across all management planes |
| Runtime auth remains delegated | Refresh/access/signing remain host-injected; signed recordings preserve `agent-task-v1` bytes |
| Global administration is server-only | Public inventory contains 130 tenant/public operations and no global-admin operation |
| Standard public errors and scopes | Coordinated server route, authorization, and PostgreSQL integration tests pass |
| Detailed immutable docs | 130 digest-bound pages and 121 secure cURL examples pass generation/static checks |
| Exhaustive endpoint tests | 130 operations × three languages = 390 strict recorded requests |
| Bounded Agent histories | Stable task/workflow cursor pages, serialized server limit, finite SDK reads, and incremental APIs pass regressions |
| Executable live policy | Fixture manager, safety guards, cleanup ledger, nightly/pre-release/production workflows, and release dependency exist |
| Passing live policy | **BLOCKED** — protected environments/scenarios and successful nightly/pre-release runs do not yet exist |
| Three release paths | Only Go, npm, and PyPI publishers; each depends on reusable validation and isolated pre-release live execution |

## Phase gate results

| Phase | Report | Result |
| --- | --- | --- |
| 0 | Server common authentication and contracts | PASS, including pagination and authentication corrections |
| 1 | Deterministic generation and inventory | PASS |
| 2 | Language package consolidation | PASS |
| 3 | Detailed API documentation and secure cURL | PASS |
| 4 | Exhaustive endpoint and live tests | **BLOCKED on external live execution evidence** |
| 5 | Unified CI and publishing cutover | PASS; publication depends on pre-release live workflow |

## Corrective review

The PR review raised two genuine blockers. Both source-code deviations are now
corrected:

1. Agent task and workflow histories no longer require unbounded HTTP
   responses. The server captures a stable snapshot boundary in an opaque,
   resource-bound cursor and constrains pages by event count and serialized
   bytes. SDK full-history methods follow cursors, while walkers/async
   generators/iterators permit bounded incremental consumption.
2. Live tiers are executable rather than labels. The fixture manager enforces
   exact contract ownership, run-prefixed resources, explicit IDs,
   triple-consent destructive calls, reverse cleanup, secret redaction, and a
   durable ledger. Workflows schedule nightly and production runs and gate all
   releases on isolated pre-release coverage.

A later Codex pass found six additional source-level regressions. All were
valid under the approved design and are corrected without weakening its auth
boundaries:

1. Legacy Agent runtime session families are revoked rather than refreshed
   without their original namespace, queue, and signing-key bindings.
2. The dashboard unwraps and follows paginated Agent event pages.
3. The Agent CLI reads the standard `message` error field with legacy fallback.
4. `postgrip agent up` consumes an administrator-issued one-time enrollment
   key; the tenant management token remains management-only.
5. Previously applied migration 0136 is restored byte-for-byte so deployment
   checksum validation remains stable.
6. TypeScript managed-runtime signing loads Node crypto only when signing is
   configured. A browser-target root-facade bundle and eager-graph regression
   prove Worker-style runtimes do not need Node compatibility.

While rebuilding the evidence, ignored output from the pre-consolidation npm
layout was also found in the local `dist` tree. TypeScript builds now clean that
tree before compiling, preventing stale files from entering an artifact.

A fresh Codex pass found four more valid, design-compatible deviations. They
are corrected in the coordinated PRs:

1. Go sandbox WebSocket handshakes now reuse the shared redirect-safe HTTP
   client, so same-host redirects to a different port or subdomain cannot
   receive management or gateway credentials. Explicit separately configured
   relay origins remain supported.
2. All terminal/runtime Agent API consumers prefer the standard `message`
   error field while retaining `error` as a legacy fallback.
3. The internal global-administration contract now includes fleet rollout
   GET/POST/DELETE operations, and its checker enforces reverse server-route
   coverage.
4. Common `agent:operate` tokens can no longer reach undocumented Agent host
   update, lifecycle, targeted-placement, or security-settings mutations.
   High-impact host actions require an owner/admin session; ordinary member
   check and poll probes remain compatible.
5. Every remaining undocumented Agent GET route that exposes host,
   credential, configuration, or browser-only history state now requires an
   organization member session. The Agent contract checker enforces reverse
   coverage so a future non-contract management route cannot silently inherit
   common-token access.
6. Migration-0140 recovery now has an explicit owner/admin rotation grant: a
   fresh key is bound atomically to the same tenant and Agent ID only when the
   caller supplies the current key hash. The old key and sessions are revoked,
   stale/cross-tenant/replayed grants fail closed, and normal enrollment still
   rejects a mismatched key.
7. Image-backed managed runtimes accept the host-injected delegated refresh
   credential and omit the variable when none is issued. The credential is
   still unavailable to shell payload allowlists and is never replaced by the
   common management token.

The next SDK review found four further deviations. Each was independently
checked against the immutable design and corrected in
`db1c7827643fb40c008573343635f093dbc7b69f`:

1. Python sandbox WebSocket redirects now compare the destination origin
   before constructing the redirected handshake, so arbitrary gateway headers
   cannot cross origins on any supported `websockets>=13` release.
2. Live targeted operations must contain the exact identifier recorded for
   their declared fixture resource; merely naming an existing ledger key is no
   longer sufficient.
3. TypeScript runtime signatures cover the final request pathname and query,
   including a configured reverse-proxy prefix.
4. TypeScript relay scheme matching is case-insensitive as required by URL
   semantics.

The same design audit corrected one adjacent error-envelope mismatch:
TypeScript Agent errors prefer the standard `message` field and use `error`
only as a legacy fallback.

The final SDK review found four valid design deviations, all corrected in
`9e35ddf2a4fbe68ec8cb3f73f6f01bb96576da14`:

1. Fixture ownership is checked against target path parameters only, so an
   identifier elsewhere in a request cannot authorize mutation of another
   object.
2. Cleanup requests are fully resolved and frozen when their resource is
   registered, preventing later captures from redirecting cleanup.
3. Creation intent is persisted before execution and finalized immediately
   from resource captures, before any unrelated response capture can fail.
4. Generated raw Python examples refuse redirects instead of forwarding the
   management bearer. The same final design audit applies explicit redirect
   refusal to the Go and TypeScript examples, and static documentation checks
   enforce all three guards across 121 generated examples.

The live gate cannot honestly be marked PASS in this change. GitHub currently
has only `github-pages`, `npm`, and `pypi` environments; no disposable URLs,
scenario secrets, host-runtime credentials, or live run evidence are
available. Recorded tests and fixture-manager self-tests are not substituted
for that evidence.

## Final evidence

- Go unified module: all packages pass `go test ./...` and `go vet ./...`.
- TypeScript: frozen install, typecheck, clean build, browser-target root
  bundle, and 126 tests pass; the npm artifact contains 95 files.
- Python: wheel builds; 128 tests pass with one opt-in external live skip;
  sandbox tests also pass against `websockets` 13.1 and 17.1, and a real
  cross-origin redirect reaches no credential-bearing target handshake.
- Contracts/docs: 130 generated operations, fixtures, and immutable pages;
  121 real cURL examples; runtime drift check passes.
- Recorded transport: 390 SDK requests validate routes, queries, headers,
  bodies, auth lanes, signing bytes, protocol ownership, and decoding.
- Agent server: full orchestrator test/vet and 45-operation OpenAPI route check
  pass, including snapshot, cross-resource, limit, byte-bound, internal-admin
  contract, standardized-error, reverse non-contract route coverage, targeted
  enrollment recovery, and host-authorization regressions. A disposable
  PostgreSQL 16 run passes the complete Agent store integration suite. The
  full dashboard suite passes 87 files / 766 tests.
- Live infrastructure: fixture-manager self-test, production allowlist
  validation, and `actionlint` 1.7.7 pass.
- Documentation: root strict MkDocs build passes.

## External release controls

The source PR is review-ready, but release remains blocked until organization
administrators configure the `sdk-live-nightly`, `sdk-live-pre-release`, and
`sdk-live-production-smoke` environments and record successful nightly and
pre-release runs for the coordinated server revision. The server must also be
merged/deployed and authenticated npm/PyPI owners must record control of the
designed registry names before any release tag is approved.
