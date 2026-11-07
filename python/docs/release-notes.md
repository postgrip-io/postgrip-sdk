# Release notes

## Unreleased

- Worker contract bundle `a20586b1…`: `WorkerClient` and `AsyncWorkerClient`
  gain `removal_impact` (`getWorkerRemovalImpact`) and `remove`
  (`removeWorker`, `workers:admin`). `removal_impact` answers what the removal
  would delete or change and its `etag`. `remove` requires `idempotency_key`
  and `if_match`, the impact's `etag`, both validated before any request. A
  changed impact answers `412` `PRECONDITION_FAILED` and a Worker with managed
  volumes `409` `WORKER_HAS_MANAGED_VOLUMES`; nothing is changed.
- Service contract bundle `0fd58ddb…`: `repositories.list_service_git_hub_accounts`
  lists the organization's connected GitHub accounts, and
  `configuration_operations.abandon_service_configuration_operation` ends a
  failed or blocked delete as `abandoned` without contacting a Worker.
  Runtime-log settings are per app per Worker:
  `update_service_runtime_log_settings` no longer takes `environment_id`, and
  `trim_service_build_logs` and `flush_service_build_logs` take an optional
  `environment_id`.
  The Compose file read answers an `etag`, and its write takes an optional
  `If-Match` (`412` when stale). Default runtime-log and traffic settings
  answer `isDefault: true`, and traffic windows add `6h` and `5d`. A project's
  repository answers `bound` and, for GitHub, `gitHubInstallationRef`, and a
  GitHub create may name `repository.installationRef`
  (`409 GITHUB_INSTALLATION_REQUIRED` or `GITHUB_INSTALLATION_MISMATCH`). A
  private GitLab or Bitbucket repository is refused with
  `422 REPOSITORY_NOT_PUBLIC`.
- Service contract bundle `cc37cae6…`: `OpenAPICreateServiceProjectRequest`
  (and `projects.create_service_project`) takes `repository` as an optional
  key. A `zvec` or `ladybugdb` project left without one is built from its
  engine's public repository; any other project still needs one and is refused with
  `400 VALIDATION`. A backend's `serverType` is `docker` or `podman`
  (`400 VALIDATION` otherwise). `OpenAPIServiceTarget` gains the read-only
  `snapshotCovered` for a connected SQLite file, and
  `OpenAPIServiceRemovalVolumeImpact` gains `mountedByDeploymentIds`.
  `checkService` answers `409` `SERVICE_AUTHENTICATION_FAILED` or
  `SERVICE_FILE_NOT_FOUND`, attaching a missing SQLite file answers `409`
  `SERVICE_FILE_NOT_FOUND`, deleting a mounted volume answers `409`
  `VOLUME_MOUNTED`, and a deployment that stays queued for 30 minutes fails
  with `errorCode` `DEPLOYMENT_QUEUE_TIMEOUT`.
- Agent `Connection` gains `cancel_task` and `TaskClient` gains `cancel`,
  which end a task that has not finished (`cancelTask`): it becomes `failed`
  with `result.failure.type` `TaskCancelled`. A finished task raises
  `409 TASK_TERMINAL` and a workflow's own task `409 TASK_OWNED_BY_WORKFLOW`.
  `postgrip.agent` exports `CancelTaskRequest`.
- Task sends, signals and signal-with-start take an optional
  `idempotency_key`: `TaskClient.enqueue`, `WorkflowClient.signal_with_start`,
  `WorkflowHandle.signal` and `signal_sync`, and `Connection.enqueue_task`,
  `signal_workflow` and `signal_with_start_workflow`. A key is sent only when
  given, is checked before sending, and lets `enable_retries` retry the send;
  the SDK never generates one. A key passed to the generated `openapi` calls
  is now checked and makes the send retryable too. A keyed
  `WorkflowClient.signal_with_start` needs an explicit `workflow_id` and raises
  `ValueError` before sending without one, because the ID it would generate
  differs on every call.
- `is_terminal_task_mutation`, which the Agent runtime uses to stop renewing a
  lease and to raise `CancelledFailure` from `activity.heartbeat()`, also reads
  a `409` with code `TASK_CANCELLED` as terminal.
- `WorkerClient` and `AsyncWorkerClient` gain `storage_destinations`, which
  lists the organization's storage destinations (`listStorageDestinations`),
  ordered by name and not paged. A destination's `id` is the
  `storageDestinationId` that `update_snapshot_settings` takes. No credential
  is answered.
- `WorkerClient` and `AsyncWorkerClient` gain the Worker snapshot operations:
  `snapshot_status`, `snapshots`, `take_snapshot`, `snapshot_settings` and
  `update_snapshot_settings`. The two mutations require `idempotency_key`.
  `take_snapshot` (and `openapi.create_worker_snapshot`) uses a 6-minute
  timeout, never less than the configured one, and never retries a `502` or
  `504`, because a resend takes another snapshot. `signingKey` is write-only:
  settings answer `hasSigningKey`.
- A managed workflow runtime's Agent `Connection` or `Client.connect` without an
  address now connects to the `POSTGRIP_AGENTORCHESTRATOR_URL` its host Agent
  injects, ahead of `POSTGRIP_AGENT_URL` and `POSTGRIP_URL`. Previously it
  ignored that address, so on installations not served by the built-in cloud
  address the runtime polled the wrong host. Outside a managed runtime, and
  with an explicit address, resolution is unchanged.
- Agent HTTP failures, including workspace uploads, raise the new exported
  `AgentAPIError`, a `PostGripAPIError` and still a `RuntimeError`, instead of a
  `RuntimeError` carrying the server body. Its `str()` and `repr()` name only
  the method, route and status; `code`, `message`, `request_id`, `details` and
  the untrusted `response_body` remain available. A response that is not valid
  JSON fails without quoting its body.
- Agent requests run through the shared executor. `Connection(enable_retries=True)`,
  which `PostGrip(enable_retries=True)` now also sets for Agent, opts into
  bounded retry of the 18 contract-annotated reads, refreshing the delegated
  session before each attempt. A long poll's timeout is its wait plus 30
  seconds. Public-lane requests (`health` and the session refresh) no longer
  send a configured `Authorization` header, and request bodies are compact JSON.
- Service requests run through the same shared executor. `ServiceAPIError`
  keeps its fields, constructor, equality and text and subclasses the shared
  `PostGripAPIError` base. The generated low-level Service operations
  (`ServiceClient.openapi`) reject a missing or invalid required
  `Idempotency-Key` before sending and forward `If-Match` only on operations
  whose contract declares it. Service `Retry-After` parsing accepts only
  non-negative delta-seconds or an HTTP date, so `+5` or `1.5` backs off with
  jitter. Request bodies are encoded as compact JSON.
- Worker requests run through a shared contract-driven executor.
  `WorkerAPIError` keeps its fields, constructor, equality and text, and now
  subclasses an internal shared `PostGripAPIError` base that the other planes
  will also use.
- The generated low-level Worker operations (`WorkerClient.openapi`) reject a
  missing or invalid required `Idempotency-Key` before sending.
- Worker `Retry-After` parsing accepts only non-negative delta-seconds or an
  HTTP date; a signed or fractional value such as `+5` or `1.5` backs off with
  jitter instead. An oversized success body now fails with
  `ValueError("PostGrip Worker response is invalid or too large")`.
- Types the Agent convenience methods on `Connection`, `Client`,
  `WorkflowClient`, `WorkflowHandle`, `TaskClient`, `ScheduleClient` and
  `SandboxClient` with the OpenAPI-generated aliases (`Task`, `Schedule`,
  `WorkflowExecution`, `TaskEvent`, `Sandbox`, …) instead of `dict[str, Any]`,
  and types their `**options` with `typing.Unpack` over new exported option
  `TypedDict`s such as `ListTasksOptions` and `WorkflowClientStartOptions`.
  Runtime behavior, keyword names and requests are unchanged, but static type
  checkers are stricter: passing a value annotated `dict[str, Any]` where a
  request `TypedDict` is expected, reading an undeclared key from a typed
  response, or passing an undeclared keyword option now reports a type error.
  Dictionary literals with the declared keys keep type-checking.

## 0.13.0

- Consolidates Agent, Worker-management, and Service-management into one
  `postgrip` PyPI distribution with singular Python submodules.
- Adds synchronous and asynchronous one-token root facades.
- Publishes immutable detailed API reference and secure cURL examples.

## 0.12.3

- Adds the `stdin` exec argument and `SandboxSession.close_input()` so commands
  that consume input through EOF can finish without closing their output side.
- Preserves valid fast-process exit statuses when the EOF control races the
  remote close.
- Standardizes the published package metadata on Apache-2.0 licensing.

## 0.12.2

- Corrects the package README's validation commands and license link for the
  monorepo layout, and refreshes Python release references.

## 0.12.1

- Changes the default service address to `https://agentorchestrator1.postgrip.io`.
  The previous default, `agentorchestrator.postgrip.app`, does not resolve, so
  any client constructed without an explicit address or environment override
  was contacting a host that does not exist. Callers that already pass an
  address, or set `POSTGRIP_AGENT_URL`, are unaffected.
- Streams file-like sandbox workspace archives instead of reading the entire
  upload into memory.
- Tests the installed wheel in CI and again before publishing, without the
  source tree shadowing the installed package.

## 0.12.0

This release completes the hard cutover to the public SDK monorepo.

- Moves source, release automation, CI, and documentation to the monorepo.
- Regenerates the OpenAPI-owned models and typed client from the canonical contract.
- Retains the existing `postgrip` PyPI package name and public API.

## 0.11.0

This release documents and packages the current managed workflow runtime model for the Python SDK.

- Adds the `workflow.runtime` submission path through `client.task.workflow_runtime(...)`.
- Documents delegated runtime credentials through `Client.connect()` inside managed runtimes.
- Documents SDK-owned workflow UI metadata stored under `postgrip.ui`.
- Covers workflow history replay, schedules, child workflows, continue-as-new, signals, queries, updates, cancellation, activity heartbeats, milestones, stdout/stderr task events, typed protocol objects, and `py.typed` packaging.
- Keeps the package version aligned with the published `v0.11.0` GitHub release.
