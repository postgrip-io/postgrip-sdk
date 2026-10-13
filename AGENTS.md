# Repository guidelines

Read the topic owners below before changing that area. These linked rules are
part of this guidance. [The documentation index](docs/index.md) assigns one
current owner per topic; dated designs and archived evidence do not override it.
Keep historical decisions in separate linked records, outside current guides.
Resolve contradictions against the code and intended invariant in the same PR.

## Repository map and commands

`go/`, `typescript/` and `python/` each publish one SDK with Agent, Worker and
Service namespaces. `contracts/` mirrors web's canonical OpenAPI specifications;
`go/protocol/` owns runtime wire types. Keep the published Go module path even
though the repository is named `postgrip-sdk`.

Use Go tooling, Bun for TypeScript and Python tooling for Python. Run the
narrowest affected suite first, then cover every affected language. Exact
commands, prerequisites and CI coverage live in the validation guide below.

## Required topic guides

| Topic | Current owner |
| --- | --- |
| MVC-ish layers, language idioms, dependency boundaries and responsibility review | [Architecture](docs/development/architecture.md) |
| OpenAPI conformance, generation, runtime wire types and web coordination | [Contracts](docs/development/contracts.md) |
| Local checks, documentation validation and actual CI coverage | [Validation and CI](docs/development/testing.md) |
| Design, PR review, findings and merge | [Contribution process](docs/development/contributing.md) |
| Management credentials and delegated sessions | [Authentication](docs/authentication.md) |
| Endpoints, precedence and paging | [Configuration](docs/configuration.md) |
| Deployed evidence, fixtures and cleanup | [Live testing](docs/live-testing.md) |
| Artifacts, version coordination and release gates | [Releasing](docs/releasing.md) |

## Non-negotiable boundaries

Use the shared MVC-ish principle: separate models, orchestration and external
adapters, with composition at the public entry point. Follow the SDK-specific
roles and language mappings in the architecture guide. OpenAPI owns HTTP wire
contracts; idiomatic clients must preserve them. Change generated files through
their generators and keep all affected languages and runtime consumers compatible.

Every implementation, including documentation, follows its living design in
`docs/design/`. Keep PRs small and single-scope, branch from `main`, and never
commit or push directly to `main`. Follow the linked contribution process through
`@codex review`, validated fixes and green CI before squash merge. Treat design
drift and responsibility violations as findings. Validate each finding by
reproducing it, and reject with evidence those that only matter for deliberately
evasive code or for files and syntax the repository does not use. Never weaken
checks or add exceptions to hide a boundary violation.

Never commit tokens, signing keys, real fixture credentials or `.env` files.
Management credentials and host-injected delegated sessions remain separate.
Keep customer secrets worker-local, Worker and Agent lifecycles separate, and
internal global-administration operations out of public SDK contracts.
