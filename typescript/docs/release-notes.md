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
