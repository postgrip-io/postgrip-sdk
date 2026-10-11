# SDK documentation acceptance evidence

Date: 2026-10-11. This is dated evidence for the
[documentation authority design](sdk-documentation-authority-20261011.md),
not another current policy owner.

## Scope and file accounting

All 62 baseline non-reference Markdown files have an explicit disposition in
the design. The baseline is SDK `bd8ea00f285bca1622c1a45484acc53ae489ba07`.
The audit covers current entry points, contributor files, language guides,
scenario documentation and their current references. Historical records were
classified and preserved; their old findings were not re-adjudicated as today's
backlog. No claim is made that every historical generated page was read anew.

| Category | Baseline | Result after all slices |
| --- | ---: | ---: |
| Non-reference Markdown files | 62 | 79 |
| Generated reference Markdown files | 8,307 | 8,307 |
| Immutable digest directories | 49 | 49 |
| Total tracked Markdown files | 8,369 | 8,386 |
| Root AGENTS lines | 60 | 28 |

The 17 additional non-reference files are four current development owners,
two dated design/evidence files, ten archived originals and an archive index.
The ten former record paths remain routing stubs. This intentionally increases
file count to separate history and preserve URLs; it is not a test-script
reduction. Twelve nested contributor/placeholder files lose 488 net lines of
duplicate or obsolete guidance. No generated bundle or public SDK API is removed.

## Delivery and review

| PR | Scope | Review evidence |
| --- | --- | --- |
| [SDK #62](https://github.com/postgrip-io/postgrip-sdk/pull/62) | Root entry and current owners | Clean Codex review; all nine CI jobs passed |
| [SDK #63](https://github.com/postgrip-io/postgrip-sdk/pull/63) | Archive ten records and separate historical navigation | Clean Codex review; all nine CI jobs passed |
| [SDK #65](https://github.com/postgrip-io/postgrip-sdk/pull/65) | Nested contributor/placeholder routing | Clean Codex review; all nine CI jobs passed |
| [SDK #64](https://github.com/postgrip-io/postgrip-sdk/pull/64) | Current usage and site corrections | Clean review of `d57e962522`; subsequent naming-only commit `d526638d` corrects MIGRATION; final CI recorded on PR |
| [Web #2124](https://github.com/postgrip-io/postgrip-web/pull/2124) | Reciprocal owners and linked coverage guides | One valid finding fixed; final documentation/policy CI and main CI passed |

The final owner reconciliation makes web's contribution guide the sole shared
PR-lifecycle owner. SDK contributing owns only its local application. This
record must land after #64 so its resulting file map describes merged work.
The closure PR records its own review and final CI; this record does not claim
its future merge result in advance.

## Verification

- All three HTTP contract mirrors compare byte-for-byte with web, including
  merged web #2124 (`830ab573d2b730e0ce93c5c16ce69b651a1b6625`). Agent has 45,
  Worker 13 and Service 123 operations; total 181. Bundle:
  `a7d0c48055260f5fbf599cc94ea78f07d5f35866ce1aa8718338bb6696b69010`.
- `python3 scripts/generate_openapi.py --plane all --check`,
  `python3 scripts/generate_api_docs.py --check`,
  `python3 scripts/check_api_docs.py`, and
  `python3 scripts/check_operation_coverage.py` pass on the integrated candidate.
  Reference checking covers the current bundle and pointer. Package READMEs
  retain their digest links because `check_api_docs.py` verifies that exact
  current digest; older generated bundles remain untouched.
- Runtime `check_drift.py --self-test` and `--monorepo` pass: 59 protocol-backed
  OpenAPI and eight runtime-only types. This is not proof of all field types or
  optionality; those remain review obligations.
- A temporary audit resolves all 141 relative destinations in the integrated
  current non-reference guides before this closure. It excludes archive bodies
  and old generated bundles; it does not claim external-URL or anchor validation.
- All ten archived records pass substantive-content parity against their
  pre-move content after removing only the historical banner and normalizing
  relocated Markdown destinations. All 35 relocated relative links resolve; all
  62 disposition targets exist. Original PASS/BLOCKED labels and unresolved
  recommendations remain intact.
- Strict MkDocs builds pass for root, TypeScript and Python. Local root builds
  took approximately 171–172 seconds. CI repeats those builds; the separate
  publishing workflow also builds Go's Jekyll site. A root MkDocs pass alone
  does not establish Go rendering.
- Thirteen Python documentation snippets compile with top-level-await support.
  Six extracted TypeScript snippets pass strict NodeNext `tsc`: two quick-start
  programs, local configuration, index, activities and continuation examples.
  Two extracted Go quick-start programs and the continuation function compile
  with `GOWORK=off go test -mod=mod ./...` in a temporary module replacing this
  SDK checkout. These are compilation checks, not live execution.
- TypeScript install/typecheck/build and Vitest pass (138 tests). Python unittest
  runs 142 tests with one existing credential-gated live smoke skipped.
  The PR CI also runs Go, Python 3.11/3.12/3.13, artifacts and recorded endpoints.
- Web typecheck, TypeScript/Go architecture validation and all documentation
  commands pass: four guards and nine consumer test files / 130 tests. The
  linked coverage-guide correction passed all documentation checks again.

## Limits and open gaps

No deployment or live SDK operation was exercised for this documentation task.
Recorded endpoint coverage and live-tier ownership are not live success evidence.
The existing Python live smoke skip and scheduled production-smoke failures do
not become passing results because documentation CI is green.

SDK CI still runs full validation on Markdown changes, uses GitHub-hosted
runners, and lacks web's action pinning, timeout and main-run cancellation
policies. Its [current CI owner](../development/testing.md) records those gaps.
No workflow behavior was changed. Enabling squash merges was the only
repository-setting change and was explicitly approved. Web's SDK source pin, contract bytes and compatibility Go import
path remain unchanged.

Example launchers retain legacy override readers and pinned remote bootstrap
commands. Their READMEs now distinguish those from current SDK configuration;
the Python launcher still assumes an old archive directory name. This cleanup
corrects and documents usage and limitations, not the live launcher implementation.
