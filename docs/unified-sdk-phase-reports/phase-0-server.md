# Phase 0 server gate

Status: **PASS**

Completed: 2026-08-25 (America/Los_Angeles)

Reviewer: Codex implementation conformance review

## Revision and contract baseline

- Design SHA-256: `4a35c1e1c89fea5a729d5d19fd00cc27824a8ae3e4cf1945d6741a382c9e0ad7`
- Implementation-plan SHA-256: `15d1d37ef4372b57477f1cecee4eb796bdc8652d7680bf36501b9b47edee266e`
- Coordinated server repository: `postgrip-web`
- Initial server contract commit: `be2b080161b58d9a294b6c5b144a8a188c162779`
- History-pagination corrective commit: `061e3ebc`
- Authentication and consumer corrective commit: `ecf0cd15`
- Contract-bundle algorithm: SHA-256 over each public contract's filename,
  NUL, exact bytes, and NUL, ordered Agent, Service, Worker
- Contract-bundle digest: `5b44c873737a135f75486b56f84cd534c0ac398dc87cdbc0150fd64c8cfcfcbd`
- Agent contract SHA-256: `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`
- Worker contract SHA-256: `f3ad25a26be9c31614261f7c950b1c84513033ad38d672a574590078adabcab9`
- Service contract SHA-256: `2dd219d428083e4416f141676dcfed63fe23f5d4d729aaadb3a574c2cb2b1ec5`

## Scope delivered

- Added the shared `pgt_` tenant-token family and a concrete cross-plane scope
  model.
- Made the persistent `worker.api_tokens` record plane-neutral and allowed one
  token to carry Agent, Worker, and Service grants.
- Added scoped common-token authentication to Agent tenant routes. The token
  record derives the tenant and inbound tenant-identity headers cannot replace
  it.
- Standardized public errors on `code`, `message`, `requestId`, and optional
  `details`.
- Classified every public contract operation and recorded credentials, scopes,
  safety, protocol, retry, idempotency, and pagination metadata.
- Removed global administration from the public Agent contract and added a
  separately owned server-admin contract.
- Kept Agent enrollment, delegated sessions, and request signing separate from
  the common tenant token.
- Added host injection of delegated refresh credentials. Refresh rotation now
  preserves namespace, queue, and ephemeral signing-key bindings.
- Retained the established public contract URLs under `/docs/api/`.
- Changed the browser token-management route to `/api/management-tokens` and
  the generated setup snippet to one `POSTGRIP_TOKEN` variable.

## Requirement traceability

| Requirement | Implementation | Test evidence |
| --- | --- | --- |
| One printable common token | `postgrip-shared/managementtoken/token.go`; Worker token issue/store adapter | shared token unit tests; Worker token lifecycle tests |
| Cross-plane concrete grants | shared scope constants and implication graph; token settings UI | Worker scope-isolation and token-creation tests |
| Agent scope matrix | Agent route policy and `agent-openapi.json` security requirements | Agent contract-to-router scope test |
| Tenant derived from token | Agent common-token lookup; Worker/Service middleware context | persistent common-token integration test; Worker tenant-header test |
| Stable auth errors | Agent and Worker/Service public error writers | Agent HTTP integration error assertions; Worker middleware tests |
| Global-admin separation | `agent-admin-openapi.json`; compact removed from public Agent spec | Agent OpenAPI checker and contract tests |
| Predictable deployed specs | Vite emitted assets and nginx SPA exclusions | OpenAPI asset and nginx route tests |
| Host-injected Agent bootstrap | host runtime environment and delegated-session refresh bindings | Agent host-runtime test; delegated refresh regression |
| Real database authentication | migration `0140_agent_auth_session_bindings.sql`; common token DB lookup | disposable PostgreSQL migration plus HTTP integration suite |

## Protocol consumer inventory

The workspace-wide import scan found these production consumers of
`github.com/postgrip-io/postgrip-agent-sdks/protocol`:

1. The current Go Agent SDK module in `postgrip-sdks/go`.
2. The host Agent runtime in `postgrip-web/postgrip-agent`.
3. The Agent Orchestrator and verifier in
   `postgrip-web/postgrip-agentorchestrator`.
4. Shared sandbox models in `postgrip-web/postgrip-shared/sandbox`.

Repository documentation and the preserved user-owned nested checkout also
contain references but are not additional deployed consumers. Phase 2 owns the
coordinated import migration after `protocol/` moves beneath the unified Go
module.

## Commands and summarized results

- All three server OpenAPI checkers, including their self-tests: passed (45
  Agent, 12 Worker, and 73 Service operations).
- `go test ./...` in the Agent Orchestrator, Worker Orchestrator, and host Agent
  modules: passed.
- `go test ./...` in the shared management-token module: passed.
- Focused UI/proxy tests: 34 passed.
- Root TypeScript typecheck: passed.
- Disposable PostgreSQL 16, all 152 migrations through
  `0140_agent_auth_session_bindings.sql`: passed.
- PostgreSQL-backed common-token lookup and real Agent HTTP authentication,
  insufficient-scope, request-ID, and invalid-token cases: passed.
- Registry metadata checks: npm `@postgrip/sdk` and PyPI `postgrip` both
  returned not found on 2026-08-25.

## Deviations and corrective actions

The design originally conflicted with the host runtime's deliberate omission
of delegated refresh tokens. Inspection showed that refresh rotation discarded
delegated namespace, queue, and signing-key claims. The server now persists and
reapplies those bindings, restores the normal short access-token TTL, and only
then injects the refresh token. Tests prove a rotated delegated session cannot
escape its namespace and retains its ephemeral signing identity.

The first implementation also retained production fallback to the old Agent
management-token table. That contradicted the one-token boundary. PostgreSQL-
backed Agent authentication now accepts only the common control-plane record;
the old path remains solely for in-memory test/development compatibility.

Post-review validation found that pre-migration runtime-session rows lacked the
delegation bindings needed for safe refresh. Migration 0140 now revokes those
legacy families, and both in-memory and PostgreSQL rotation reject any
unbound row. Fresh enrollment persists the Agent's explicit namespace, queue,
and signing-key bindings. The same corrective revision restores migration 0136
byte-for-byte, follows paginated Agent event logs in the dashboard, reads the
standard error envelope in the CLI, and makes `agent up` consume a separately
issued one-time enrollment key instead of trying to turn a tenant management
token into a runtime credential.

No unresolved Phase 0 implementation deviations remain.

## Remaining risks

- The available npm and PyPI names have not been reserved because no
  authenticated registry publisher identity is present. The responsible owner
  is the PostGrip organization release administrator. Merge and release remain
  blocked until that owner records reservation/ownership evidence.
- The coordinated server commit is tested in a local disposable environment
  but is not yet deployed. The server PR must merge and deploy before the SDK
  PR merges or any unified package is published.
