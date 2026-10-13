# MVC-ish SDK contributor guidance

Status: documentation scope; runtime migration is separate.

## Problem and scope

The SDK already uses web's concise AGENTS entry point and shared contribution
process, but its architecture owner does not explicitly map the MVC-ish
principle to SDK roles or provide a responsibility review checklist. Make the
shared principle mandatory while adapting it to Go, TypeScript and Python.
Specify admission requirements for a future language without claiming one is
already supported.

Audit AGENTS and its referenced current guides for semantic agreement as part
of this scope. Correct configuration and authentication claims against source;
do not change runtime behavior to make an inaccurate documentation claim true.
Follow references recursively through current SDK guides, including language
site navigation and same-repository GitHub/Pages URLs. Inventory all current
SDK Markdown so guides outside that link graph also receive a disposition.
At historical records and generated references, record the boundary and the
appropriate checks instead of treating them as new policy owners. Check shared
web policy for SDK applicability; unrelated web product documentation remains
owned by web.

## Design

- Match web's current AGENTS structure: repository map and commands, required
  topic guides and non-negotiable boundaries. Linked guides remain normative.
- Keep [architecture](../development/architecture.md) the single SDK owner of
  models, orchestration, generated bindings, adapters and composition rules.
  An SDK has no rendering layer. Language idioms may differ; OpenAPI wire meaning
  and runtime protocol compatibility must remain consistent.
- Keep [contracts](../development/contracts.md) authoritative for canonical
  web schemas, mirror regeneration and coordinated revisions. Keep web's
  contribution guide authoritative for PR review rounds and merge thresholds;
  [SDK contributing](../development/contributing.md) applies its lifecycle and
  responsibility review locally without duplicating it.
- Document actual checker limits and existing coupling. The separate
  [transport layering proposal](https://github.com/postgrip-io/postgrip-sdk/pull/69) remains a
  proposal; this guidance does not implement its executor or behavior changes.
- Preserve one artifact per supported language. A future language requires a
  scoped design, three-plane contract coverage, protocol parity, validation and
  release integration, including changes to current package checks.
- Keep current constructor precedence, timeout/retry differences and Agent
  credential-selection limits in their configuration/authentication owners.
  Link required architecture and open gaps without presenting planned fixes
  as delivered. Keep release admission and documentation-review requirements
  consistent with those owners.

## Validation and acceptance

Compare with current web `AGENTS.md`, `code-review/architecture.md` and
`docs/development/contributing.md`. Check claims against root constructors,
generated client boundaries and `scripts/check_package_layout.py`. Review local
links and overlapping current guides; run generated documentation checks and
all three strict MkDocs builds per [validation](../development/testing.md).
No executable behavior, generated artifacts or web SDK pins change in this
scope. Deliver as one documentation PR under the shared review process.

The [recursive reference audit](sdk-mvcish-guidance-audit.md) records the exact
document inventory, source evidence, corrections and validation limits.
