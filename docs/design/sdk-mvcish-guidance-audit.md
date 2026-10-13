# SDK guidance recursive reference audit

Date: 2026-10-12 (America/Los_Angeles). Base SDK revision: `eb63e55c8153666fda0104ce57eefb5367866898`.
This is maintenance evidence for [the guidance design](sdk-mvcish-guidance.md),
not another policy owner or a claim of runtime/release readiness.

## Scope and traversal

The baseline inventory contains 66 tracked Markdown files outside
`docs/reference/`, `docs/archive/` and `docs/design/`: 52 current guides/entry
points, 10 historical routing stubs, three release-note histories and one
generated operation-coverage report. Every file has a disposition below.
The archive index was also read to verify its non-normative boundary.

The recursive link walk starts at AGENTS and resolves relative links,
same-repository GitHub URLs, published language-site URLs and Go Jekyll
`relative_url` links. It reaches 36 inventory files; the remaining 30 are
included explicitly, covering site-navigation pages, example guides and
contributor/test entry points. The inventory therefore does not depend on a
page being reachable by an inline Markdown link. After corrections, the 66
files contain 203 resolved local reference edges with no missing destinations.
The unmerged transport design is linked through PR #69 so this guidance can
be reviewed independently from `main`.

Current guides were compared for agreement on ownership, MVC-ish roles,
contracts, language/package support, authentication, configuration, validation
and the PR/release process. This is a documentation-consistency audit with
focused source verification, not an exhaustive correctness audit of every
runtime method mentioned by the guides.

Historical archive contents, release history and past acceptance records are
terminal evidence, not current instructions to rewrite. Active designs are
proposals checked for status and consistency with current owners; they do not
establish delivered behavior. Generated current API pages are checked by the
generator and reference validators, not claimed as 181 independent manual
runtime reviews. Old immutable bundles retain their historical URLs.

External registry, language/tool documentation, release pages and unrelated
web product/deployment guides are external references, not SDK policy owners.
This audit does not claim to review all documentation in other repositories or
verify registry publication and live service behavior.

## Shared web policy

The SDK-relevant architecture, PR lifecycle, contract coordination and CI
comparison were checked against web's current owners, not the older sibling
working tree. GitHub content blob SHAs at review:

| Web owner | Blob SHA |
| --- | --- |
| `AGENTS.md` | `df0b9ddea83e4fb6b8e533f0f41fefa66fc801f4` |
| `code-review/architecture.md` | `ccf5cf95f36b1ec144d583b2af7810caca4476e5` |
| `docs/development/contributing.md` | `5d9bcbddd6cfcee53befe757333479e97db565b8` |
| `docs/development/api-contracts.md` | `ed0a7d35890f7fec85e2770357adbc6d724e8870` |
| `docs/development/ci.md` | `bba3700f5b4b76c7dc087e3547d5c657e8ad678c` |

Web's reference index, conventions and applicable invariant sections informed
scope and interpretation. Its UI, database, deployment and runner rules are not
silently imported into SDK requirements. Shared review rounds remain owned by
web; SDK-specific commands and responsibility checks remain owned here.

## Corrections and source evidence

| Conflicting or incomplete claim | Correction and evidence |
| --- | --- |
| MVC-ish had no explicit SDK mapping or review checklist | Architecture now defines models, orchestration, bindings, adapters and composition with Go/TypeScript/Python mappings. Generated schema/binding colocation is distinguished from handwritten mixed responsibilities. |
| All root constructors share precedence | Configuration, root README and Go/TypeScript introductions now agree with Go `New`/`NewFromEnv`, TypeScript `resolvePostGripConfig` and Python `resolve_config`. |
| Omitting an Agent URL always selects the cloud default | All three installation guides now account for plane and common environment fallbacks in Go `NewConnection`, TypeScript `Connection.create` and Python `Connection.__init__`. |
| A root token implies management-only Agent credentials | Authentication and root README describe Go/Python environment credential selection and TypeScript runtime configuration, following the Agent constructors and request auth-lane selection. |
| Common timeout/retry behavior is already implemented | Configuration describes current root forwarding and plane eligibility; the proposed transport design remains separate. |
| All Agent HTTP failures use the structured error base | TypeScript/Python API guides and authentication now match their `Connection` error paths and `PostGripAgentError` subclasses. `TaskFailedError` carries task ID/message, not an underlying `ApplicationFailure` field. |
| Go package arrows and shared transport ownership were unclear | Package guide arrows now mean consumer-to-dependency and include `go/internal/transport`, checked against production imports. |
| Node/npm alone runs the repository build | TypeScript installation identifies `bun run clean` inside `package.json`'s build script. |
| Numeric Service retry caps belong to OpenAPI | Go Service guide attributes numeric caps to `client.go`; the contract annotations govern eligibility. |
| Adding a fourth language conflicts with a fixed three-artifact rule | Architecture and releasing distinguish current support from required future generator, validation and release integration. |
| Closed schemas exclude explicitly declared maps | Contract guidance preserves canonical open-ended fields, matching `additionalProperties` in the mirrors. |

Other retained guides agree with these topic owners at the reviewed policy
boundaries. Runtime guides keep language-specific workflow mechanics; fixture
and release guides keep their explicit consent and evidence requirements.

## File dispositions

“Reviewed” means checked for the policy agreement described above, not that
all runtime examples were executed against a deployed service.

| Baseline file | Disposition |
| --- | --- |
| `AGENTS.md` | Reviewed and corrected/aligned in this change. |
| `MIGRATION.md` | Reviewed; retained. |
| `README.md` | Reviewed and corrected/aligned in this change. |
| `docs/authentication.md` | Reviewed and corrected/aligned in this change. |
| `docs/configuration.md` | Reviewed and corrected/aligned in this change. |
| `docs/curl.md` | Reviewed; retained. |
| `docs/development/architecture.md` | Reviewed and corrected/aligned in this change. |
| `docs/development/contracts.md` | Reviewed and corrected/aligned in this change. |
| `docs/development/contributing.md` | Reviewed and corrected/aligned in this change. |
| `docs/development/testing.md` | Reviewed and corrected/aligned in this change. |
| `docs/index.md` | Reviewed and corrected/aligned in this change. |
| `docs/live-testing.md` | Reviewed; retained. |
| `docs/releasing.md` | Reviewed and corrected/aligned in this change. |
| `docs/unified-sdk-design.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-implementation-plan.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/final-integration.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-0-server.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-1-generation.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-2-packages.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-3-documentation.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-4-endpoint-tests.md` | Historical routing stub; archive boundary verified. |
| `docs/unified-sdk-phase-reports/phase-5-ci-release.md` | Historical routing stub; archive boundary verified. |
| `docs/worker-bootstrap.md` | Reviewed; retained. |
| `go/CLAUDE.md` | Reviewed; retained. |
| `go/README.md` | Reviewed and corrected/aligned in this change. |
| `go/agent/doc/README.md` | Reviewed; retained. |
| `go/agent/docs/api.md` | Reviewed; retained. |
| `go/agent/docs/index.md` | Reviewed; retained. |
| `go/agent/docs/installation.md` | Reviewed and corrected/aligned in this change. |
| `go/agent/docs/packages.md` | Reviewed and corrected/aligned in this change. |
| `go/agent/docs/quickstart.md` | Reviewed; retained. |
| `go/agent/docs/release-notes.md` | Historical release record; retained as history. |
| `go/agent/docs/workflow-runtime.md` | Reviewed; retained. |
| `go/agent/example/README.md` | Reviewed; retained. |
| `go/protocol/AGENTS.md` | Reviewed; retained. |
| `go/protocol/CLAUDE.md` | Reviewed; retained. |
| `go/protocol/README.md` | Reviewed; retained. |
| `go/protocol/doc/README.md` | Reviewed; retained. |
| `go/protocol/test/README.md` | Reviewed; retained. |
| `go/service/README.md` | Reviewed and corrected/aligned in this change. |
| `go/test/README.md` | Reviewed; retained. |
| `go/worker/README.md` | Reviewed; retained. |
| `python/CLAUDE.md` | Reviewed; retained. |
| `python/README.md` | Reviewed; retained. |
| `python/doc/README.md` | Reviewed; retained. |
| `python/docs/api.md` | Reviewed and corrected/aligned in this change. |
| `python/docs/index.md` | Reviewed; retained. |
| `python/docs/installation.md` | Reviewed and corrected/aligned in this change. |
| `python/docs/quickstart.md` | Reviewed; retained. |
| `python/docs/release-notes.md` | Historical release record; retained as history. |
| `python/docs/workflow-runtime.md` | Reviewed; retained. |
| `python/example/README.md` | Reviewed; retained. |
| `simplification-report.md` | Historical routing stub; archive boundary verified. |
| `test/live/README.md` | Reviewed; retained. |
| `test/reports/operation-coverage.md` | Generated inventory; checked by coverage/reference validators. |
| `typescript/CLAUDE.md` | Reviewed; retained. |
| `typescript/README.md` | Reviewed and corrected/aligned in this change. |
| `typescript/doc/README.md` | Reviewed; retained. |
| `typescript/docs/api.md` | Reviewed and corrected/aligned in this change. |
| `typescript/docs/index.md` | Reviewed; retained. |
| `typescript/docs/installation.md` | Reviewed and corrected/aligned in this change. |
| `typescript/docs/quickstart.md` | Reviewed; retained. |
| `typescript/docs/release-notes.md` | Historical release record; retained as history. |
| `typescript/docs/workflow-runtime.md` | Reviewed; retained. |
| `typescript/example/README.md` | Reviewed; retained. |
| `typescript/test/README.md` | Reviewed; retained. |

## Validation

Passed during this audit:

- `python3 scripts/generate_api_docs.py --check`: 181 operations, current bundle `a7d0c4805526…`.
- `python3 scripts/check_api_docs.py`: 181 operation pages and 172 cURL examples.
- `python3 scripts/check_operation_coverage.py`: 181 owned operations, including nine protocol exceptions; this does not execute live tests.
- `python3 scripts/check_package_layout.py`: current Go/npm/PyPI layout.
- Recursive local reference mapping: no missing destinations among the 203 edges above.
- Strict MkDocs builds for the root, TypeScript and Python sites.
- Initial local reference/anchor validation: 198 references across 69 inventory, boundary and audit files.
- `git diff --check`.

Go's Jekyll-specific navigation is resolved to source pages
by the link walk; MkDocs does not build the Go site. No live calls, registry
publishing, runtime refactor or web source-pin update is part of this audit.
