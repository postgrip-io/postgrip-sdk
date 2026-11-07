---
title: Release notes
layout: default
nav_order: 7
---

# Release notes

## Unreleased

- Service contract bundle `5dba38d5…`: a failed deployment's `errorCode` is one
  of a closed set: `BUILD_FAILED`, `IMAGE_PULL_FAILED`, `HEALTHCHECK_FAILED`,
  `REQUIRED_SECRET_MISSING`, `WORKER_LOST`, `DEPLOYMENT_QUEUE_TIMEOUT`, or
  `DEPLOYMENT_FAILED` for anything unclassified. `errorMessage` is a fixed
  sentence per code, never the Worker's text; the build log keeps the detail.
  The types do not change.
- Worker contract bundle `a20586b1…`: `worker.Client` gains `RemovalImpact`
  (`getWorkerRemovalImpact`) and `Remove` (`removeWorker`, `workers:admin`).
  `RemovalImpact` answers what the removal would delete or change and its
  `Etag`. `Remove` takes `RemoveOptions` with the required `IdempotencyKey`
  and `IfMatch`, the impact's `Etag`, both validated before any request. A
  changed impact answers `412` `PRECONDITION_FAILED` and a Worker with managed
  volumes `409` `WORKER_HAS_MANAGED_VOLUMES`; nothing is changed. The Worker
  client now forwards `If-Match` where an operation declares it.
- Service contract bundle `0fd58ddb…`: `ServiceRepositoriesClient.ListGitHubAccounts`
  lists the organization's connected GitHub accounts, and
  `ServiceConfigurationOperationsClient.Abandon` ends a failed or blocked
  delete as `abandoned` without contacting a Worker. Runtime-log settings are
  per app per Worker: `ServiceRetentionClient.UpdateRuntime` and
  `OpenAPIClient.UpdateServiceRuntimeLogSettings` no longer take a query
  (`OpenAPIUpdateServiceRuntimeLogSettingsQuery` is removed), and `TrimBuild`,
  `FlushBuild`, `TrimServiceBuildLogs` and `FlushServiceBuildLogs` take an
  `OpenAPITrimServiceBuildLogsQuery` or `OpenAPIFlushServiceBuildLogsQuery`
  with an optional `EnvironmentId`. `OpenAPIPutServiceComposeFileHeaders` gains
  an optional `IfMatch`.
  The Compose file read answers an `etag`, and its write takes an optional
  `If-Match` (`412` when stale). Default runtime-log and traffic settings
  answer `isDefault: true`, and traffic windows add `6h` and `5d`. A project's
  repository answers `bound` and, for GitHub, `gitHubInstallationRef`, and a
  GitHub create may name `repository.installationRef`
  (`409 GITHUB_INSTALLATION_REQUIRED` or `GITHUB_INSTALLATION_MISMATCH`). A
  private GitLab or Bitbucket repository is refused with
  `422 REPOSITORY_NOT_PUBLIC`.
- Service contract bundle `cc37cae6…`: `service.OpenAPICreateServiceProjectRequest.Repository`
  is now an optional `*OpenAPIServiceRepositoryWriteRequest` (`omitempty`)
  instead of a required value; callers that set it take its address. A `zvec`
  or `ladybugdb` project left without one is built from its engine's public
  repository; any other project still needs one and is refused with
  `400 VALIDATION`. A backend's `ServerType` is `docker` or `podman`
  (`400 VALIDATION` otherwise). `OpenAPIServiceTarget` gains the read-only
  `SnapshotCovered *bool` for a connected SQLite file, and
  `OpenAPIServiceRemovalVolumeImpact` gains `MountedByDeploymentIds`.
  `checkService` answers `409` `SERVICE_AUTHENTICATION_FAILED` or
  `SERVICE_FILE_NOT_FOUND`, attaching a missing SQLite file answers `409`
  `SERVICE_FILE_NOT_FOUND`, deleting a mounted volume answers `409`
  `VOLUME_MOUNTED`, and a deployment that stays queued for 30 minutes fails
  with `ErrorCode` `DEPLOYMENT_QUEUE_TIMEOUT`.
- `client.Connection` gains `CancelTask` and `client.TaskClient` gains
  `Cancel`, which end a task that has not finished (`cancelTask`): it becomes
  `failed` with `result.failure.type` `TaskCancelled`. A finished task fails
  with `409 TASK_TERMINAL` and a workflow's own task with
  `409 TASK_OWNED_BY_WORKFLOW`. The body is the new `protocol.CancelTaskRequest`
  (alias `client.CancelTaskRequest`).
- Task sends, signals and signal-with-start take an optional `Idempotency-Key`:
  `EnqueueInput.IdempotencyKey`, `SignalWithStartOptions.IdempotencyKey`, or
  `client.WithIdempotencyKey(ctx, key)` for `WorkflowHandle.Signal` and the
  `Connection` calls. A key is sent only when given, is checked before
  sending, and lets `EnableRetries` retry the send; the SDK never generates
  one. `OpenAPI().Do` now forwards a header the operation declares, and still
  refuses any other.
- The Go `worker.Worker` stops a task whose heartbeat answers `409
  TASK_CANCELLED`, or says the task is terminal or no longer leased: the task
  context is cancelled, renewal stops and nothing is reported. Previously it
  ran the task to the end and logged the refused report. `activity.Heartbeat`
  returns a `*failure.Cancelled` for the same answer, as in TypeScript and
  Python. Other heartbeat failures are still only logged.
- `worker.Client` gains `StorageDestinations`, which lists the organization's
  storage destinations (`listStorageDestinations`), ordered by name and not
  paged. A destination's `Id` is the `StorageDestinationId` that
  `UpdateSnapshotSettings` takes. No credential is answered.
- `worker.Client` gains the Worker snapshot operations: `SnapshotStatus`,
  `Snapshots`, `TakeSnapshot`, `SnapshotSettings` and `UpdateSnapshotSettings`.
  The two mutations require an idempotency key. `TakeSnapshot` (and
  `OpenAPI().CreateWorkerSnapshot`) raises the HTTP client's timeout to 6
  minutes for the call and never retries a `502` or `504`, because a resend
  takes another snapshot. `SigningKey` is write-only: settings answer
  `HasSigningKey`.
- A managed workflow runtime's `client.NewConnection` with an empty `Address`
  now connects to the `POSTGRIP_AGENTORCHESTRATOR_URL` its host Agent injects,
  ahead of `POSTGRIP_AGENT_URL` and `POSTGRIP_URL`. Previously it ignored that
  address, so on installations not served by the built-in cloud address the
  runtime polled the wrong host. Outside a managed runtime, and with an
  explicit `Address`, resolution is unchanged.
- `protocol.PollTaskResponse`, `protocol.Sandbox`, `protocol.TaskResult` and
  `protocol.SandboxCreateRequest` (and their `client` aliases) keep an explicit
  JSON `null` for their optional nullable properties when a decoded value is
  re-encoded. A decoded `TaskResult` no longer re-encodes absent
  `started_at`/`finished_at` as year-one timestamps. Values built in code
  encode exactly as before.
- A `SandboxCreateRequest` decoded from JSON that omits `resourceLimits` or
  `networkPolicy` now sends them omitted instead of as zero-valued objects
  while they remain zero; values assigned after decoding are sent. Both
  properties are optional in the contract.
- Source compatibility: the four types gained an unexported field, so unkeyed
  composite literals of them, such as `protocol.PollTaskResponse{task, nil}`,
  no longer compile; keyed literals are unaffected. Their new `MarshalJSON`
  and `UnmarshalJSON` methods are promoted to structs that embed them
  anonymously, so such a wrapper's own JSON fields are neither encoded nor
  decoded.

## v0.13.0

- Consolidates Agent, Worker-management, Service-management, and protocol
  packages into one Go module with one-token root-client configuration.
- Adds deterministic generated clients and immutable detailed API reference
  pages for all three public planes.
- Preserves the published Go module path for compatibility.

## v0.12.3

- Signals stdin EOF after `SandboxClient.Exec` drains its input so commands
  that read to EOF can finish while output and exit-status delivery stay open.
- Adds `SandboxStream.CloseWrite` for manually managed exec sessions.
- Preserves valid fast-process exit statuses when the EOF control races the
  remote close, and pins the shared wire contract at `protocol/v0.3.1`.

## v0.12.2

- Aligns the Go SDK release number with the TypeScript and Python SDK releases.
  There are no Go API or wire-contract changes from v0.12.1.

## v0.12.1

- Changes the default service address to `https://agentorchestrator1.postgrip.io`.
  The previous default, `agentorchestrator.postgrip.app`, does not resolve, so
  any client constructed without an explicit address or environment override
  was contacting a host that does not exist. Callers that already pass an
  address, or set `POSTGRIP_AGENT_URL`, are unaffected.

## v0.12.0

This release completes the hard cutover to the public SDK monorepo.

- Changes the module path to `github.com/postgrip-io/postgrip-agent-sdks/go`.
- Pins the consolidated protocol module at `protocol/v0.3.0`.
- Moves source, releases, CI, and documentation to the monorepo.
- Removes the retired `go.postgrip.io/sdk` vanity-module dependency.

## v0.11.0

This release documents and tags the current managed workflow runtime model for the Go SDK.

- Adds the `workflow.runtime` submission path through `client.Task.WorkflowRuntime`.
- Documents delegated runtime credentials for managed runtimes launched by a host PostGrip agent.
- Documents SDK-owned workflow UI metadata stored under `postgrip.ui`.
- Covers workflow history replay, schedules, child workflows, continue-as-new, signals, cancellation, activity heartbeats, milestones, stdout/stderr task events, structured failures, and determinism checks.
- Keeps the Go module tag aligned with the published `v0.11.0` GitHub release.
