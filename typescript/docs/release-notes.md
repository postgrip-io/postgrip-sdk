# Release notes

## Unreleased

- Worker requests run through a shared contract-driven executor. Each exchange
  is bounded at 30 seconds by default (`WorkerClientConfig.timeoutMs`), and an
  earlier `AbortSignal` abort still wins.
- `WorkerAPIError` keeps its fields, constructor and `name`; it now extends an
  internal shared API error base that the other planes will also use.
- The generated low-level Worker operations (`WorkerClient.openapi`) reject a
  missing or invalid required `Idempotency-Key` before sending.
- Worker `Retry-After` parsing ignores signed values such as `+5`, which are
  not valid delta-seconds, and backs off with jitter instead.
- Service requests run through the same executor. Each exchange is bounded at
  30 seconds by default (`ServiceClientConfig.timeoutMs`), and an earlier
  `AbortSignal` abort still wins. `ServiceAPIError` keeps its fields,
  constructor and `name` and extends the same internal base.
- The generated low-level Service operations (`ServiceClient.openapi`) reject a
  missing or invalid required `Idempotency-Key` before sending, and forward
  `If-Match` only on operations whose contract declares it.
- Service `Retry-After` parsing accepts only non-negative delta-seconds or an
  HTTP date; other values, such as `+5` or `1e1`, back off with jitter.
- Agent HTTP failures, including workspace uploads, raise the new exported
  `AgentAPIError` (a `PostGripAPIError`) instead of `Error`. Its text names only
  the method, route and status, without server content; `code`, `requestId`,
  `details` and the untrusted `responseBody` remain available. A response that
  is not valid JSON fails without quoting its body.
- Agent requests run through the shared executor: each exchange is bounded at
  30 seconds by default (`ConnectionOptions.timeoutMs`), a long poll at its wait
  plus 30 seconds, and `ConnectionOptions.enableRetries` opts into bounded
  retry of the 18 contract-annotated reads, refreshing the delegated session
  before each attempt.
- `PostGripConfig` gains `timeoutMs`, passed to every plane, and passes
  `enableRetries` to Agent as well as Worker and Service.
- Agent requests send `Accept: application/json`, a `Content-Type` configured in
  `ConnectionOptions.headers` now replaces the default, and public-lane requests
  (`health` and the session refresh) no longer send a configured
  `Authorization` header.

## 0.13.0

- Consolidates Agent, Worker-management, and Service-management into one
  `@postgrip/sdk` npm package with singular subpath exports.
- Adds the one-token `PostGrip` root facade and deterministic generated
  clients for all three planes.
- Publishes immutable detailed API reference and secure cURL examples.

## 0.12.3

- Adds the `stdin` exec option and `SandboxSession.closeInput()` so commands
  that consume input through EOF can finish without closing their output side.
- Preserves valid fast-process exit statuses when the EOF control races the
  remote close, with cleanup for genuine stdin setup failures.
- Standardizes the published package metadata on Apache-2.0 licensing.

## 0.12.2

- Adds a prominent installation section to the npm README.
- Corrects the repository layout and documents the implemented cancellation
  scope support and active Vitest suite.

## 0.12.1

- Changes the default service address to `https://agentorchestrator1.postgrip.io`.
  The previous default, `agentorchestrator.postgrip.app`, does not resolve, so
  any client constructed without an explicit address or environment override
  was contacting a host that does not exist. Callers that already pass an
  address, or set `POSTGRIP_AGENT_URL`, are unaffected.
- Authenticates sandbox WebSocket relay handshakes with the configured
  management token and custom connection headers on Node and Bun.
- Adds `webSocketFactory` for custom authenticated relay transports and reports
  the native browser WebSocket header limitation before creating a session.

## 0.12.0

This release completes the hard cutover to the public SDK monorepo.

- Moves source, release automation, CI, and documentation to the monorepo.
- Regenerates the OpenAPI-owned models and typed client from the canonical contract.
- Retains the Agent API under the `@postgrip/sdk/agent` subpath.

## 0.11.0

This release documents and packages the current managed workflow runtime model for the TypeScript SDK.

- Adds the `workflow.runtime` submission path for handing SDK runtimes to an existing PostGrip agent pool.
- Documents delegated runtime credentials through `Connection.connect()` inside managed runtimes.
- Documents SDK-owned workflow UI metadata stored under `postgrip.ui`.
- Covers workflow history replay, schedules, child workflows, continue-as-new, signals, queries, updates, cancellation, activity heartbeats, milestones, and task output events.
- Keeps the package version aligned with the published `v0.11.0` GitHub release.
