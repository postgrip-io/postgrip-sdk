# Phase 5 checkpoint: CI and release cutover

Status: **PASS**

Completed: 2026-08-26

Design SHA-256: `c381af949ea5da1378462c1a130d8fb43742e6cd3ab7fd246111210e8471aa6a`

Implementation-plan SHA-256: `e548a76a725210f116fe0663df40b421c4260d4a9a8c7cd35c6c5730d429e32e`

Contract-bundle SHA-256: `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`

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
| Go module source | 102 files, 14 packages | 838,392 bytes | `github.com/coder/websocket` | 0.075 s inspection |
| npm package | 131 files | 149,244 packed / 1,355,645 unpacked bytes | `ws` | 1.212 s build + 0.580 s inspection |
| Python wheel | 36 files | 89,035 bytes | `cryptography>=42` | 0.459 s build |

The npm tarball was installed into an empty project and imported through the
root plus all singular subpaths. The Python wheel was installed into an empty
virtual environment and imported through the root plus all singular
submodules. The Go module passed `GOWORK=off` test, vet, and package listing.

## Design comparison and corrective actions

The end-of-phase comparison found and corrected four deviations before this
checkpoint passed:

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

After these corrections, no unexplained Phase 5 design deviation remains.

## Verification

| Check | Result |
| --- | --- |
| `actionlint` 1.7.7 over every workflow | PASS |
| `python3 scripts/check_release_artifacts.py --ecosystem all` | PASS — three artifacts |
| Go `GOWORK=off` test, vet, and list | PASS — 14 packages |
| TypeScript typecheck, test, build, pack, clean install/import | PASS — 120 tests |
| Python wheel build and clean install/import | PASS — 36 wheel files |
| Package layout guard | PASS — exactly three manifests |
| Version parity | PASS — 0.13.0 in root, Go, npm, and PyPI metadata |
| Contract digest parity | PASS — all nine plane/language bindings |

## Remaining release controls

No release tag was created. The protected `sdk-release`, `npm`, and `pypi`
environments must not approve publication until Phase 4's disposable nightly
and isolated pre-release live suites are implemented and pass, the coordinated
server PR is merged/deployed, and authenticated registry owners record
ownership evidence. The absent live suites are tracked as a blocking Phase 4
design deviation in the final integration report.
