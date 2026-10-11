# Repository guidelines

This repository publishes one SDK per language from `go/`, `typescript/` and
`python/`, with Agent, Worker and Service namespaces. HTTP contracts mirror
`postgrip-web`; runtime wire types live in `go/protocol/`. Keep the published
Go module path even though the repository is named `postgrip-sdk`.

Read the current owner before changing a topic:

- [Architecture and style](docs/development/architecture.md)
- [Contracts and web coordination](docs/development/contracts.md)
- [Validation and CI](docs/development/testing.md)
- [Contribution and review process](docs/development/contributing.md)
- [Authentication](docs/authentication.md) and [configuration](docs/configuration.md)
- [Live testing](docs/live-testing.md) and [releasing](docs/releasing.md)

[The documentation index](docs/index.md) routes to all other current guides.
Link to these owners rather than duplicating their rules. Historical evidence
belongs in separate records referenced by current guides, never as current policy.

Use small, single-scope PRs from a design in `docs/design/`. Follow the linked
review loop through `@codex review`, validated fixes and green CI before squash
merge. Never commit directly to `main` or bypass checks to make CI pass.

Never commit tokens, signing keys, real fixture credentials or `.env` files.
Management credentials and host-injected delegated sessions remain separate.
Generated files change through their generators; all affected languages and
coordinated runtime consumers must remain compatible.
