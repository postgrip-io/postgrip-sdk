# Release notes

## Unreleased

- Service contract bundle `30423932…`: an HTTP service (web, backend, ZVEC or
  LadybugDB) takes its credential through `putTargetServiceConnection`.
  `administration.targets.putConnection` keeps its signature; its body
  (`OpenAPITargetServiceConnectionRequest`) carries exactly one of `password`
  (PostgreSQL), now optional, or the new `http`
  (`OpenAPITargetServiceHTTPCredential`: `scheme` one of `none`, `basic`,
  `bearer` or `api_key`, with `username` and `password`, `token`, or
  `headerName` and `value`; `none` clears it). Sending `http` needs a Worker
  with `target_http_auth_v1`, otherwise `409 WORKER_UPGRADE_REQUIRED`.
  `ServiceTarget` gains `httpAuth` (`OpenAPITargetServiceHTTPAuth`: `scheme`,
  with `username` for `basic` and `headerName` for `api_key`, never a
  secret). `checkService` probes an HTTP service with one `GET` from its
  Worker: the answer gains `httpStatus`, and a `401` or `403` is
  `409 SERVICE_AUTHENTICATION_FAILED`. The service entry exports
  `OpenAPITargetServiceHTTPCredential` and `OpenAPITargetServiceHTTPAuth`.
- Service contract bundle `5dba38d5…`: a failed deployment's `errorCode` is one
  of a closed set: `BUILD_FAILED`, `IMAGE_PULL_FAILED`, `HEALTHCHECK_FAILED`,
  `REQUIRED_SECRET_MISSING`, `WORKER_LOST`, `DEPLOYMENT_QUEUE_TIMEOUT`, or
  `DEPLOYMENT_FAILED` for anything unclassified. `errorMessage` is a fixed
  sentence per code, never the Worker's text; the build log keeps the detail.
  The types do not change.
- Worker contract bundle `a20586b1…`: `WorkerClient` gains `removalImpact`
  (`getWorkerRemovalImpact`) and `remove` (`removeWorker`, `workers:admin`).
  `removalImpact` answers what the removal would delete or change and its
  `etag`. `remove(workerId, { idempotencyKey, ifMatch })` takes the impact's
  `etag` as `ifMatch`; both fences are validated before any request. A changed
  impact answers `412` `PRECONDITION_FAILED` and a Worker with managed volumes
  `409` `WORKER_HAS_MANAGED_VOLUMES`; nothing is changed. The Worker entry
  publishes `RemoveWorkerOptions`, `OpenAPIWorkerRemovalImpact`,
  `OpenAPIWorkerRemovalImpactProject`, `OpenAPIWorkerRemovalUnreachableVolume`,
  `OpenAPIWorkerRemovalCleanup`, `OpenAPIRemoveWorkerResponse` and the two
  operations' request and response body types.
- Service contract bundle `0fd58ddb…`: `repositories.listGitHubAccounts`
  lists the organization's connected GitHub accounts
  (`listServiceGitHubAccounts`), and `configurationOperations.abandon` ends a
  failed or blocked delete as `abandoned` without contacting a Worker
  (`abandonServiceConfigurationOperation`). Runtime-log settings are per app
  per Worker: `retention.updateRuntime` no longer takes a query, so it is now
  `updateRuntime(serviceId, body, options)`. `retention.trimBuild` and
  `retention.flushBuild` take an optional trailing `{ environmentId }` query.
  The Compose file read answers an `etag`, and its write takes an optional
  `If-Match` (`412` when stale). Default runtime-log and traffic settings
  answer `isDefault: true`, and traffic windows add `6h` and `5d`. A project's
  repository answers `bound` and, for GitHub, `gitHubInstallationRef`, and a
  GitHub create may name `repository.installationRef`
  (`409 GITHUB_INSTALLATION_REQUIRED` or `GITHUB_INSTALLATION_MISMATCH`). A
  private GitLab or Bitbucket repository is refused with
  `422 REPOSITORY_NOT_PUBLIC`.
- Service contract bundle `cc37cae6…`: `OpenAPICreateServiceProjectRequest`
  (and `projects.create`) takes `repository` as optional. A `zvec` or
  `ladybugdb` project left without one is built from its engine's public
  repository; any other project still needs one and is refused with
  `400 VALIDATION`. A backend's `serverType` is `docker` or `podman`
  (`400 VALIDATION` otherwise). `OpenAPIServiceTarget` gains the read-only
  `snapshotCovered` for a connected SQLite file, and
  `OpenAPIServiceRemovalVolumeImpact` gains `mountedByDeploymentIds`.
  `checkService` answers `409` `SERVICE_AUTHENTICATION_FAILED` or
  `SERVICE_FILE_NOT_FOUND`, attaching a missing SQLite file answers `409`
  `SERVICE_FILE_NOT_FOUND`, deleting a mounted volume answers `409`
  `VOLUME_MOUNTED`, and a deployment that stays queued for 30 minutes fails
  with `errorCode` `DEPLOYMENT_QUEUE_TIMEOUT`.
- Agent `Connection` gains `cancelTask` and `TaskClient` gains `cancel`, which
  end a task that has not finished (`cancelTask`): it becomes `failed` with
  `result.failure.type` `TaskCancelled`. A finished task fails with
  `409 TASK_TERMINAL` and a workflow's own task with
  `409 TASK_OWNED_BY_WORKFLOW`. The Agent entry publishes `CancelTaskRequest`,
  `OpenAPICancelTaskRequest`, the `CancelTask` request and response body types
  and `IdempotencyOptions`.
- Task sends, signals and signal-with-start take an optional
  `idempotencyKey`: `TaskClient.enqueue`, `WorkflowClient.signalWithStart`,
  and an options argument on `Connection.enqueueTask`, `signalWorkflow` and
  `signalWithStartWorkflow`; the generated `openapi` calls forward an
  `Idempotency-Key` header. A key is sent only when given, is checked before
  sending, and lets `enableRetries` retry the send; the SDK never generates
  one. A keyed `WorkflowClient.signalWithStart` needs an explicit `workflowId`
  and fails before sending without one, because the ID it would generate
  differs on every call.
- `isTerminalTaskMutation`, which the Agent runtime uses to stop renewing a
  lease, also reads a `409` with code `TASK_CANCELLED` as terminal.
- `WorkerClient` gains `storageDestinations`, which lists the organization's
  storage destinations (`listStorageDestinations`), ordered by name and not
  paged. A destination's `id` is the `storageDestinationId` that
  `updateSnapshotSettings` takes. No credential is answered. The Worker entry
  publishes `OpenAPIStorageDestination`, `OpenAPIStorageDestinationList` and
  the `ListStorageDestinations` request and response body types.
- `WorkerClient` gains the Worker snapshot operations: `snapshotStatus`,
  `snapshots`, `takeSnapshot`, `snapshotSettings` and `updateSnapshotSettings`.
  The two mutations require `idempotencyKey`. `takeSnapshot` (and
  `openapi.createWorkerSnapshot`) is allowed a 6-minute exchange, never less
  than `timeoutMs`, and never retries a `502` or `504`, because a resend takes
  another snapshot. `signingKey` is write-only: settings answer `hasSigningKey`.
- A managed workflow runtime's Agent `Connection.create` or `Connection.connect`
  without a `baseUrl` now connects to the `POSTGRIP_AGENTORCHESTRATOR_URL` its
  host Agent injects, ahead of `POSTGRIP_AGENT_URL` and `POSTGRIP_URL`.
  Previously it ignored that address, so on installations not served by the
  built-in cloud address the runtime polled the wrong host. Outside a managed
  runtime, and with an explicit `baseUrl`, resolution is unchanged.
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
