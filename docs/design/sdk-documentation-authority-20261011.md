# SDK documentation authority and web synchronization

Date: 2026-10-11. Status: implementation in focused slices.

## Problem and boundaries

SDK contributor files duplicate rules, current navigation promotes a proposed
unification design and an old active phase plan, and language guides still teach
retired management credentials. Current owners must reflect executable behavior
and share a coordinated contract/review process with web.

Baseline: SDK `bd8ea00f285bca1622c1a45484acc53ae489ba07`, web
`3db48a1525203fda5a65d0a05816210aa298e31b`. The three contract mirrors match
byte-for-byte: Agent 45, Worker 13, Service 123 operations (181 total).
The generated current bundle is
`a7d0c48055260f5fbf599cc94ea78f07d5f35866ce1aa8718338bb6696b69010`;
README's old `368948ce…` label does not match its target.

Inventory: 8,369 tracked Markdown files: 62 outside `docs/reference/`, and
8,307 inside it. Review all 62 for current ownership or historical disposition.
Validate the current generated bundle and pointer with its generator; preserve
older immutable digest directories. This is not a semantic re-audit of every
historical generated page, nor a re-run of all live SDK scenarios.

## Target ownership

`AGENTS.md` is concise mandatory guidance plus links. `docs/index.md` is the
current owner map. Development guides own architecture, contracts, checks and
PR process. Authentication, configuration, cURL, bootstrap, live scenarios,
releasing and consumer migration retain focused owners. Language guides own
language-specific examples/replay; local CLAUDE/AGENTS files route to owners.

Historical unification proposals, phase reports and the dated simplification
report move under `docs/archive/`, with preserved results and a clear historical
banner. Old URLs get short routing stubs; current navigation points directly
to the archive index. Release notes remain explicitly historical. Still-current
release/rollback requirements remain in releasing/migration; archiving an old
BLOCKED report neither clears a release gate nor claims deployment success.

Web owns canonical HTTP contracts and its SDK pin/discovery procedure. SDK
owns mirrors, generated clients and published artifacts. Cross-link owners;
keep the compatibility Go module path. Correct repository/Pages URLs to the
verified `postgrip-sdk` name without rewriting immutable historical evidence.
Do not move SDK source pins for prose-only changes.

SDK workflows currently use GitHub-hosted runners and run full CI for docs.
Web's self-hosted pool, path selection and enforcement are not SDK facts.
Document these differences rather than claiming synchronization by copying
inaccurate CI prose. Workflow behavior changes are a separate scope.

## Focused delivery slices

1. Governance: concise root entry, current owner map and four development guides.
2. History: archive original records, preserve links and current release gates;
   replace duplicate contributor/placeholder guidance with owner links.
3. Usage: fix current language setup/examples, current reference routing and
   documentation-site URLs; remove duplicated release/configuration claims.
4. Web: reciprocal SDK-owner links and verified repository naming in its
   current contract guide; record cross-repository byte comparison.

Each slice follows the review loop in `development/contributing.md`: a scoped
PR, self-review, Codex review, validated fixes, green CI and squash merge.

## File-level disposition

Every baseline non-reference Markdown file appears below. Retain means preserve
its topic, not blindly endorse old examples. Corrections must have source or
observable validation evidence. These are documentation decisions, not test
script retain/merge decisions from the earlier black-box testing project.

| As-is file | Decision | To-be file | Reason |
| --- | --- | --- | --- |
| `AGENTS.md` | Rewrite | `AGENTS.md` | Concise navigation and mandatory rules; commands/process owned by topic guides. |
| `MIGRATION.md` | Split | `MIGRATION.md` | Retain consumer migration/rollback; release procedure links to releasing owner. |
| `README.md` | Rewrite | `README.md` | Current owner navigation; eliminate stale digest label and active historical-policy links. |
| `docs/authentication.md` | Retain | `docs/authentication.md` | Current cross-language topic owner; normalize repository links where needed. |
| `docs/configuration.md` | Retain | `docs/configuration.md` | Current cross-language topic owner; normalize repository links where needed. |
| `docs/curl.md` | Retain | `docs/curl.md` | Current cross-language topic owner; normalize repository links where needed. |
| `docs/index.md` | Rewrite | `docs/index.md` | Current owner navigation; eliminate stale digest label and active historical-policy links. |
| `docs/live-testing.md` | Rewrite | `docs/live-testing.md` | Link generated operation count and fixture-manager cleanup owner instead of duplicating them. |
| `docs/releasing.md` | Retain | `docs/releasing.md` | Current release gates remain; historical evidence is linked separately. |
| `docs/unified-sdk-design.md` | Archive | `docs/archive/unified-sdk-design.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-implementation-plan.md` | Archive | `docs/archive/unified-sdk-implementation-plan.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/final-integration.md` | Archive | `docs/archive/unified-sdk-phase-reports/final-integration.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-0-server.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-0-server.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-1-generation.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-1-generation.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-2-packages.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-2-packages.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-3-documentation.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-3-documentation.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-4-endpoint-tests.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-4-endpoint-tests.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/unified-sdk-phase-reports/phase-5-ci-release.md` | Archive | `docs/archive/unified-sdk-phase-reports/phase-5-ci-release.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `docs/worker-bootstrap.md` | Rewrite | `docs/worker-bootstrap.md` | Use current reference pointer; preserve durable journal requirement and typed examples. |
| `go/CLAUDE.md` | Rewrite | `go/CLAUDE.md` | Route to root rules and current architecture/contracts owners; remove competing instructions. |
| `go/README.md` | Retain/correct | `go/README.md` | Preserve focused package introduction; link stable reference index and current topic owners. |
| `go/agent/doc/README.md` | Rewrite | `go/agent/doc/README.md` | Replace empty future-documentation placeholder with current documentation entry. |
| `go/agent/docs/api.md` | Rewrite | `go/agent/docs/api.md` | Link unified current owners; correct public entry wording and source/release links. |
| `go/agent/docs/index.md` | Rewrite | `go/agent/docs/index.md` | Link unified current owners; correct public entry wording and source/release links. |
| `go/agent/docs/installation.md` | Rewrite | `go/agent/docs/installation.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `go/agent/docs/packages.md` | Rewrite | `go/agent/docs/packages.md` | Correct Agent package subtree; retain Go-specific responsibilities. |
| `go/agent/docs/quickstart.md` | Rewrite | `go/agent/docs/quickstart.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `go/agent/docs/release-notes.md` | Retain | `go/agent/docs/release-notes.md` | Explicitly historical version notes; current pages link out rather than embed them. |
| `go/agent/docs/workflow-runtime.md` | Retain/correct | `go/agent/docs/workflow-runtime.md` | Own language-specific replay semantics; correct source-verified examples and remove duplicate CLAUDE prose. |
| `go/agent/example/README.md` | Rewrite | `go/agent/example/README.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `go/protocol/AGENTS.md` | Rewrite | `go/protocol/AGENTS.md` | Route to root rules and current architecture/contracts owners; remove competing instructions. |
| `go/protocol/CLAUDE.md` | Rewrite | `go/protocol/CLAUDE.md` | Route to root rules and current architecture/contracts owners; remove competing instructions. |
| `go/protocol/README.md` | Rewrite | `go/protocol/README.md` | Fix module-local license/mirror links and route contract maintenance to its owner. |
| `go/protocol/doc/README.md` | Rewrite | `go/protocol/doc/README.md` | Replace empty future-documentation placeholder with current documentation entry. |
| `go/protocol/test/README.md` | Rewrite | `go/protocol/test/README.md` | Replace obsolete reserved-test prose with actual test locations and validation owner. |
| `go/service/README.md` | Retain/correct | `go/service/README.md` | Preserve focused package introduction; link stable reference index and current topic owners. |
| `go/test/README.md` | Rewrite | `go/test/README.md` | Replace obsolete reserved-test prose with actual test locations and validation owner. |
| `go/worker/README.md` | Retain/correct | `go/worker/README.md` | Preserve focused package introduction; link stable reference index and current topic owners. |
| `python/CLAUDE.md` | Rewrite | `python/CLAUDE.md` | Route to root rules and current architecture/contracts owners; remove competing instructions. |
| `python/README.md` | Retain/correct | `python/README.md` | Preserve focused package introduction; link stable reference index and current topic owners. |
| `python/doc/README.md` | Rewrite | `python/doc/README.md` | Replace empty future-documentation placeholder with current documentation entry. |
| `python/docs/api.md` | Rewrite | `python/docs/api.md` | Link unified current owners; correct public entry wording and source/release links. |
| `python/docs/index.md` | Rewrite | `python/docs/index.md` | Link unified current owners; correct public entry wording and source/release links. |
| `python/docs/installation.md` | Rewrite | `python/docs/installation.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `python/docs/quickstart.md` | Rewrite | `python/docs/quickstart.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `python/docs/release-notes.md` | Retain | `python/docs/release-notes.md` | Explicitly historical version notes; current pages link out rather than embed them. |
| `python/docs/workflow-runtime.md` | Retain/correct | `python/docs/workflow-runtime.md` | Own language-specific replay semantics; correct source-verified examples and remove duplicate CLAUDE prose. |
| `python/example/README.md` | Rewrite | `python/example/README.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `simplification-report.md` | Archive | `docs/archive/simplification-report.md` | Dated proposal/evidence; preserve original results and unresolved recommendations, link current owners. |
| `test/live/README.md` | Retain | `test/live/README.md` | Own scenario grammar, consent, cleanup failures and remaining-resource evidence. |
| `test/reports/operation-coverage.md` | Retain generated | `test/reports/operation-coverage.md` | Generated count owner: 181 operations; live columns are assignments, not successful live evidence. |
| `typescript/CLAUDE.md` | Rewrite | `typescript/CLAUDE.md` | Route to root rules and current architecture/contracts owners; remove competing instructions. |
| `typescript/README.md` | Retain/correct | `typescript/README.md` | Preserve focused package introduction; link stable reference index and current topic owners. |
| `typescript/doc/README.md` | Rewrite | `typescript/doc/README.md` | Replace empty future-documentation placeholder with current documentation entry. |
| `typescript/docs/api.md` | Rewrite | `typescript/docs/api.md` | Link unified current owners; correct public entry wording and source/release links. |
| `typescript/docs/index.md` | Rewrite | `typescript/docs/index.md` | Link unified current owners; correct public entry wording and source/release links. |
| `typescript/docs/installation.md` | Rewrite | `typescript/docs/installation.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `typescript/docs/quickstart.md` | Rewrite | `typescript/docs/quickstart.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `typescript/docs/release-notes.md` | Retain | `typescript/docs/release-notes.md` | Explicitly historical version notes; current pages link out rather than embed them. |
| `typescript/docs/workflow-runtime.md` | Retain/correct | `typescript/docs/workflow-runtime.md` | Own language-specific replay semantics; correct source-verified examples and remove duplicate CLAUDE prose. |
| `typescript/example/README.md` | Rewrite | `typescript/example/README.md` | Correct management token/setup and observable examples against constructors/runtime methods. |
| `typescript/test/README.md` | Rewrite | `typescript/test/README.md` | Replace obsolete reserved-test prose with actual test locations and validation owner. |

## Validation and acceptance

For each slice, check relative Markdown destinations and changed behavioral
claims against current source. Run all three strict MkDocs builds and generator
checks; Go's separate Jekyll build remains a distinct publishing check. Compare
all three contract bytes with the recorded web revision, run runtime drift
self-tests and local mirror checks. Run affected language validation when
changing executable examples. Preserve generated output and public API bytes.

Record exact commands, results, source symbols, reviewed PRs and any limits in
a dated acceptance record linked from this design after completion. Do not
present recorded transport checks as live production verification. Audit all
62 disposition rows and recurse through their current topic links; stop at
explicitly historical records and immutable old generated bundles.
