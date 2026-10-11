# PostGrip SDK documentation

One SDK per language for Agent, Worker and Service, using one `POSTGRIP_TOKEN`.
Each topic below has one current owner. Source code, contracts and workflows
establish behavior; a historical report does not override them.

| Topic | Current owner |
| --- | --- |
| Install and root-client examples | [Repository quick start](https://github.com/postgrip-io/postgrip-sdk/blob/main/README.md) |
| Authentication and credential lanes | [Authentication](authentication.md) |
| Endpoints, precedence and paging | [Configuration](configuration.md) |
| Safe raw HTTP examples | [cURL](curl.md) |
| Durable Worker registration | [Worker bootstrap](worker-bootstrap.md) |
| Generated operations and exact bundle | [API reference index](reference/README.md) |
| SDK boundaries and style | [Architecture](development/architecture.md) |
| Canonical contracts and web synchronization | [Contracts](development/contracts.md) |
| Local checks and actual CI behavior | [Validation](development/testing.md) |
| Design, PR review and documentation ownership | [Contributing](development/contributing.md) |
| Live tiers | [Live testing](live-testing.md) |
| Scenario format, resource ownership and cleanup | [Fixture manager](https://github.com/postgrip-io/postgrip-sdk/blob/main/test/live/README.md) |
| Artifact publishing and current release gates | [Releasing](releasing.md) |
| Consumer migration | [Migration](https://github.com/postgrip-io/postgrip-sdk/blob/main/MIGRATION.md) |

Language guides own language-specific installation, Agent examples and replay
semantics: [Go](https://postgrip-io.github.io/postgrip-sdk/go/),
[TypeScript](https://postgrip-io.github.io/postgrip-sdk/typescript/),
[Python](https://postgrip-io.github.io/postgrip-sdk/python/).
Their release notes are historical records, not current configuration guidance.

Review the affected owner's linked current references as part of a change.
Do not recursively reopen old generated bundles or past acceptance records
unless the change depends on them. Designs specify scoped changes; they do not
become a second permanent owner after implementation.

## Historical decisions

[Archived decisions and evidence](archive/index.md) remain available separately.
