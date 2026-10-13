# API

Selected public APIs re-exported from `postgrip.agent`; the source export list
linked below is the complete inventory.

## Top-level

| Name                                                                                                                       | Purpose                                                       |
|:---------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------|
| `Client`                                                                                                                   | High-level entrypoint; group of Task / Workflow / Schedule sub-clients. |
| `Connection`                                                                                                               | HTTP transport. Most code reaches for `Client.connect(...)` instead. |
| `Agent`                                                                                                                    | Polling agent; leases tasks and dispatches workflow / activity bodies. |
| `Worker`                                                                                                                   | Backwards-compat alias to `Agent` for code mirroring the Temporal naming. |
| `WorkflowHandle`, `WorkflowUpdateHandle`                                                                                   | Durable references to workflow runs / in-flight updates.     |
| `TaskClient`, `WorkflowClient`, `ScheduleClient`                                                                           | Sub-clients accessed via `client.task`, `client.workflow`, `client.schedule`. |

## Decorators

| Name                                                                       | Purpose                                                  |
|:---------------------------------------------------------------------------|:---------------------------------------------------------|
| `@workflow.defn`                                                           | Marks a class as a workflow definition. Triggers the AST sandbox. |
| `@workflow.run`                                                            | Marks the entrypoint coroutine on a `@workflow.defn` class.       |
| `workflow.define_signal(name)` / `define_query(name)` / `define_update(name)` | Declare a signal / query / update name; returns a definition.    |
| `workflow.set_handler(definition, handler)`                                | Bind a handler method to a definition. Call from `__init__` so each replay re-registers. |
| `@activity.defn`                                                           | Marks an async function as an activity definition.        |

## Workflow runtime helpers (call from inside `@workflow.run`)

| Name                                                                                | Purpose                                                  |
|:------------------------------------------------------------------------------------|:---------------------------------------------------------|
| `workflow.now()`                                                                    | Workflow-deterministic current time.                     |
| `await workflow.sleep(d)`                                                           | Durable timer. Replaces `asyncio.sleep` in workflow code.|
| `await workflow.execute_activity(name_or_fn, *args, ...)`                           | Schedule an activity, suspend until completion.          |
| `await workflow.execute_child(workflow_class, *args, ...)`                 | Schedule a child workflow.                               |
| `await workflow.condition(lambda: ..., timeout=None)`                          | Suspend until the predicate is true (or timeout).        |
| `workflow.continue_as_new(*args)`                                                   | Restart the current workflow with fresh history.         |
| `workflow.milestone(name, index=..., total=...)`                                    | Emit a milestone event for the workflow task.            |
| `workflow.info()`                                                                   | Workflow id, run id, task queue, type.                   |
| `CancellationScope`                                                                 | Wrap an `async with` block to scope cancellation.        |

## Activity helpers (call from inside an `@activity.defn` body)

| Name                                                                       | Purpose                                                  |
|:---------------------------------------------------------------------------|:---------------------------------------------------------|
| `await activity.heartbeat(details=None)`                                   | Long-running activities ping this on a timer. Raises `CancelledFailure` if the runtime service has requested cancellation. |
| `await activity.milestone(name, index=..., total=...)`                     | Emit a milestone event for the activity task.            |
| `await activity.stdout(data, stage=..., details=...)`                      | Emit stdout output for the current activity task.        |
| `await activity.stderr(data, stage=..., details=...)`                      | Emit stderr output for the current activity task.        |
| `activity.info()`                                                          | Task id, activity type.                                  |

## Errors

| Name                                                                       | Purpose                                                  |
|:---------------------------------------------------------------------------|:---------------------------------------------------------|
| `ApplicationFailure`                                                       | Structured failure with type tag + retryability + details.|
| `CancelledFailure`                                                         | Runtime cancelled the task.                              |
| `TimeoutFailure`                                                           | Operation exceeded its deadline.                         |
| `TaskFailedError`                                                          | Terminal task failure carrying a task ID and message. |
| `PostGripAgentError`                                                       | Base class for the structured workflow/activity failure types. |
| `AgentAPIError`                                                            | Failed Agent HTTP exchange (also a `RuntimeError`): `status`, `code`, `request_id`, `details`, untrusted `response_body`; text excludes server content. |

Constructors / predicates: `ApplicationFailure(message, type=, non_retryable=, details=)`; check with `isinstance(err, ApplicationFailure)`.

Agent HTTP failures raise `AgentAPIError` rather than this hierarchy. See the
[authentication and failure owner](https://github.com/postgrip-io/postgrip-sdk/blob/main/docs/authentication.md#failure-behavior)
for current transport-error behavior and diagnostic-content handling.

## Wire types

The `postgrip.agent.types` module mirrors the Go [`protocol`](https://github.com/postgrip-io/postgrip-sdk/tree/main/go/protocol) wire shapes as Python dataclasses / TypedDicts. Common ones (`Task`, `WorkflowExecution`, `WorkflowHistoryEvent`, `RetryPolicy`, `Schedule`, `FailureInfo`) are also re-exported at the top level.

When in doubt, the code is the documentation:

- [`src/postgrip/agent/__init__.py`](https://github.com/postgrip-io/postgrip-sdk/blob/main/python/src/postgrip/agent/__init__.py) — full re-export list.
- [`src/postgrip/agent/types.py`](https://github.com/postgrip-io/postgrip-sdk/blob/main/python/src/postgrip/agent/types.py) — wire-type definitions.

## Type checking

The package ships with `py.typed` so [mypy](https://mypy-lang.org/) and [pyright](https://github.com/microsoft/pyright) pick up annotations on every public name without extra configuration.

The `Connection`, `Client`, `WorkflowClient`, `WorkflowHandle`, `TaskClient`,
`ScheduleClient` and `SandboxClient` convenience methods take and return the
OpenAPI-generated aliases rather than `dict[str, Any]`: for example
`enqueue_task(request: EnqueueTaskRequest) -> Task`, `list_tasks(...) -> list[Task]`,
`get_workflow(...) -> WorkflowExecution`, `get_task_events(...) -> list[TaskEvent]`,
`create_schedule(request: CreateScheduleRequest) -> Schedule` and
`poll_task_response(...) -> PollTaskResponse`. Paged reads return
`TaskEventPage` and `WorkflowHistoryPage`; `SandboxClient.list()` and
`list_workspaces()` unwrap their envelopes to `list[Sandbox]` and
`list[SandboxWorkspace]`.

Keyword `**options` are typed with `typing.Unpack` over these `TypedDict`s,
exported from `postgrip.agent` so callers can annotate their own option
dictionaries. Every key is optional, and the accepted keyword names are
unchanged:

| Options                        | Methods                                                     |
|:-------------------------------|:------------------------------------------------------------|
| `ConnectionOptions`            | `Connection.connect`, `Client.connect`                      |
| `ListTasksOptions`             | `Connection.list_tasks`                                     |
| `ListSchedulesOptions`         | `Connection.list_schedules`, `ScheduleClient.list`          |
| `ListWorkflowsOptions`         | `Connection.list_workflows`                                 |
| `CountWorkflowsOptions`        | `Connection.count_workflows`                                |
| `WorkflowListOptions`          | `WorkflowClient.list`                                       |
| `WorkflowCountOptions`         | `WorkflowClient.count`                                      |
| `WorkflowClientStartOptions`   | `WorkflowClient.start`, `WorkflowClient.signal_with_start`  |
| `WorkflowClientExecuteOptions` | `WorkflowClient.execute`                                    |
| `ClientStartWorkflowOptions`   | `Client.start_workflow`                                     |
| `ClientExecuteWorkflowOptions` | `Client.execute_workflow`                                   |

User data stays open: workflow and activity `args` remain `list[Any]`, and
payload, memo, search-attribute and result values keep the generated
`JsonValue` (`Any`). These annotations are static shapes only; the SDK does not
validate requests against them at runtime.
