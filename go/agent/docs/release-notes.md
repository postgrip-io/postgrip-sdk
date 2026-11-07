---
title: Release notes
layout: default
nav_order: 7
---

# Release notes

## Unreleased

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
