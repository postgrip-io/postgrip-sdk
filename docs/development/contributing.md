# SDK contribution and review

The shared design, PR review, findings and merge procedure has one owner:
[web's contribution and review process](https://github.com/postgrip-io/postgrip-web/blob/main/docs/development/contributing.md).
Follow that lifecycle for SDK work, including documentation. Its Codex review
rounds, validated-finding thresholds and green-CI squash-merge requirement apply
here; do not maintain a second copy of those rules.

## SDK application of the shared process

- Designs live in this repository's `docs/design/`. Cite the design and its
  implemented slice in each small, single-concern PR.
- Replace web-specific build/test commands with [SDK validation](testing.md).
  Start with affected suites, check runtime drift, and cover every language
  whose behavior changes. Web-only UI/Go-service checks do not run in this repo.
- Review responsibilities against [SDK architecture](architecture.md), public
  exports and [contract coordination](contracts.md). Web remains authoritative
  for server contract changes and its pinned SDK source; SDK owns its mirrors,
  generated clients and artifact validation.
- The PR's affected areas are SDK packages and transport/runtime/generator
  boundaries. Report compatibility, observable impact, coordinated PRs, exact
  commands/results and evidence limits using the shared PR requirements.
- [SDK CI](testing.md#executable-ci-owners) documents actual workflows and open
  gaps. Web runner routing and Markdown selection are not SDK guarantees.

When the shared process changes, review this SDK application and its referenced
checks alongside the web owner. Update local differences, not a copied lifecycle.

## Documentation ownership

[The documentation index](../index.md) assigns each current topic one owner.
Link to that owner instead of copying its rules into README, AGENTS, CLAUDE,
language introductions or historical records. Validate behavioral statements
against the implementation, including linked current guides; link checks alone
cannot establish semantic agreement.

Current guides describe current requirements, rationale and open gaps. Put
historical decisions, rollout chronology and past validation in separate records,
linked under **Historical decisions**. A past pass is not a current guarantee;
retain applicable rollback requirements and unresolved release gates in their
current owner. Generated reference bundles retain their immutable URLs.
