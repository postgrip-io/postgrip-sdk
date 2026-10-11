> Historical record. Original status, findings and validation below describe
> the recorded revision, not current policy or current release clearance. See
> [current owners](../../index.md) and [release gates](../../releasing.md).

# Phase 5 checkpoint: CI and release cutover

Status: **PASS**

Completed: 2026-08-26

Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`

Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`

Contract-bundle SHA-256: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`

## Delivered

- Replaced plane-specific CI with one reusable unified validation workflow.
  It checks contracts, generation, documentation, cURL, every recorded SDK
  endpoint, native builds/tests/coverage, package boundaries, strict docs, and
  release artifacts.
- Replaced eight obsolete release paths with exactly three publishing
  workflows: Go, TypeScript/npm, and Python/PyPI.
- Made all release workflows call the same reusable validation before they can
  publish. Tags are limited to `go/v*`, `typescript/v*`, and `python/v*` and
  must equal the root/package version.
- Made every release workflow depend on the protected isolated pre-release
  live suite. A tag cannot reach an artifact or publishing job if that suite
  is absent, rejected, or fails.
- Added scheduled disposable-nightly and production-safe smoke workflows. The
  production job uses a checked-in hard-coded allowlist containing only two
  public read-only health operations.
- Added artifact inspection for version, registry name, manifest cardinality,
  embedded contract digest, namespace contents, direct dependencies, size,
  file count, and build/inspection time. CI uploads the machine-readable report.
- Added reviewed artifact limits so unexpected package growth fails instead of
  silently shipping.
- Added installed-package smoke tests for root, Agent, Worker, and Service
  namespaces and matching embedded contract digests.
- Added protected publication environments and documented the coordinated
  server-deployment and registry-owner approvals required before tags are
  published. npm and PyPI use trusted publishing.
- Updated repository-local contributor guidance for the consolidated package
  tree and three authentication lanes.

## Release shape

| Ecosystem | Manifest | Tag | Workflow |
| --- | --- | --- | --- |
| Go | `go/go.mod` | `go/v0.13.0` | `publish-go.yml` |
| npm | `typescript/package.json` | `typescript/v0.13.0` | `publish-typescript.yml` |
| PyPI | `python/pyproject.toml` | `python/v0.13.0` | `publish-python.yml` |

No protocol, Worker, Service, or other plane-specific publishing manifest or
workflow remains.

## Artifact evidence

| Artifact | Contents | Size | Direct runtime dependencies | Local build/inspection |
| --- | ---: | ---: | --- | ---: |
| Go module source | 103 files, 14 packages | 847,178 bytes | `github.com/coder/websocket` | 0.126 s inspection |
| npm package | 95 files | 126,507 packed / 969,103 unpacked bytes | `ws` | 1.297 s build + 0.326 s inspection |
| Python wheel | 36 files | 89,456 bytes | `cryptography>=42` | 0.462 s build |

The npm tarball was installed into an empty project and imported through the
root plus all singular subpaths. The Python wheel was installed into an empty
virtual environment and imported through the root plus all singular
submodules. The Go module passed `GOWORK=off` test, vet, and package listing.

## Design comparison and corrective actions

The end-of-phase comparison and subsequent review found and corrected six
deviations before this checkpoint passed:

1. CI still referenced removed nested Go modules and six former npm/PyPI
   packages. Those jobs and their license/version assumptions were replaced
   with the unified tree.
2. Release automation still accepted protocol and plane-specific tags. The
   obsolete workflows were removed and the release-artifact checker now fails
   unless exactly three publishing workflows and manifests exist.
3. Existing publishers tested source trees but did not prove installed root
   and plane imports or digest parity. Packed npm and built-wheel smokes now run
   outside the source tree before publication.
4. The Go contributor guide still described the pre-consolidation module and
   two-lane transport. It now documents the root facade, language-local
   packages, and public/management/delegated lanes.
5. Incremental TypeScript builds could retain ignored outputs from the old
   package layout. Builds now clean `dist` first, and CI browser-bundles the
   root facade to prove managed-runtime Node signing is not eagerly reachable.
6. Go sandbox WebSocket handshakes bypassed the shared HTTP client's exact-origin
   redirect policy. They now reuse that client, preventing credential forwarding
   across redirect origins while preserving explicitly configured relay origins.
7. Python's supported WebSocket client range did not uniformly refuse
   cross-origin redirects carrying arbitrary gateway headers. A pre-handshake
   origin guard now covers `websockets` 13 through 17 and is verified against
   both dependency branches plus a real redirect target.
8. TypeScript signed an operation-relative path instead of the final path
   behind a reverse proxy. Signing now uses the exact URL pathname and query
   sent by `fetch`; mixed-case relay schemes are normalized according to URL
   semantics, and Agent error decoding prefers the standard `message` field.

Corrections 7 and 8 are recorded in
`db1c7827643fb40c008573343635f093dbc7b69f`.

After these corrections, no unexplained Phase 5 design deviation remains.

## Verification

| Check | Result |
| --- | --- |
| `actionlint` 1.7.7 over every workflow | PASS |
| `python3 scripts/check_release_artifacts.py --ecosystem all` | PASS — three artifacts |
| Go `GOWORK=off` test, vet, and list | PASS — 14 packages |
| TypeScript typecheck, test, clean build, browser bundle, pack, clean install/import | PASS — 126 tests; 95 package files |
| Python wheel build and clean install/import | PASS — 36 wheel files |
| Package layout guard | PASS — exactly three manifests |
| Version parity | PASS — 0.13.0 in root, Go, npm, and PyPI metadata |
| Contract digest parity | PASS — all nine plane/language bindings |

## Remaining release controls

No release tag was created. The live workflows and publication dependency now
exist, but the repository currently has no `sdk-live-nightly`,
`sdk-live-pre-release`, or `sdk-live-production-smoke` GitHub Environments and
therefore no passing live execution evidence. An organization administrator
must configure those protected environments and scenarios. Publication also
remains conditional on coordinated server deployment and authenticated
registry-owner evidence.
