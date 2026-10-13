# Release notes

## Unreleased

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
