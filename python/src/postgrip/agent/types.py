from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
# Underscored so `from postgrip.agent.types import *` cannot shadow a caller's
# `datetime` module import.
from datetime import datetime as _datetime, timedelta as _timedelta
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict

from . import openapi as _openapi

TaskState: TypeAlias = _openapi.OpenAPITaskState
TaskEventKind: TypeAlias = _openapi.OpenAPITaskEventKind
ScheduleState: TypeAlias = _openapi.OpenAPIScheduleState
ScheduleOverlapPolicy: TypeAlias = _openapi.OpenAPIScheduleOverlapPolicy
ScheduleMissedRunPolicy: TypeAlias = _openapi.OpenAPIScheduleMissedRunPolicy
CancellationType: TypeAlias = Literal["try_cancel", "wait_cancellation_completed", "abandon"]
CancellationScopeType: TypeAlias = Literal["cancellable", "non_cancellable"]
WorkflowIdReusePolicy: TypeAlias = _openapi.OpenAPIWorkflowIdReusePolicy
# Isolation tiers a workflow.runtime workload can require. A requested tier is
# a floor: container work may run in a stronger tier, microvm work must never
# run in a weaker one, and an unrecognized value satisfies nothing.
IsolationTier: TypeAlias = Literal["container", "microvm"]
WorkflowFunction: TypeAlias = Callable[..., Awaitable[Any] | Any]
ActivityFunction: TypeAlias = Callable[..., Awaitable[Any] | Any]
WorkflowRegistry: TypeAlias = dict[str, WorkflowFunction]
ActivityRegistry: TypeAlias = dict[str, ActivityFunction]

# OpenAPI component models without legacy handwritten counterparts.
JsonValue: TypeAlias = _openapi.OpenAPIJsonValue
HealthResponse: TypeAlias = _openapi.OpenAPIHealthResponse
ReadyResponse: TypeAlias = _openapi.OpenAPIReadyResponse
AgentPollDirectiveType: TypeAlias = _openapi.OpenAPIAgentPollDirectiveType
AgentPollDirectiveSubject: TypeAlias = _openapi.OpenAPIAgentPollDirectiveSubject
WorkflowState: TypeAlias = _openapi.OpenAPIWorkflowState
CreateNamespaceRequest: TypeAlias = _openapi.OpenAPICreateNamespaceRequest
HeartbeatTaskRequest: TypeAlias = _openapi.OpenAPIHeartbeatTaskRequest
AppendTaskEventRequest: TypeAlias = _openapi.OpenAPIAppendTaskEventRequest
CompleteTaskRequest: TypeAlias = _openapi.OpenAPICompleteTaskRequest
BlockTaskRequest: TypeAlias = _openapi.OpenAPIBlockTaskRequest
FailTaskRequest: TypeAlias = _openapi.OpenAPIFailTaskRequest
RefreshAgentSessionRequest: TypeAlias = _openapi.OpenAPIRefreshAgentSessionRequest
AgentSessionResponse: TypeAlias = _openapi.OpenAPIAgentSessionResponse
ErrorResponse: TypeAlias = _openapi.OpenAPIErrorResponse


FailureInfo: TypeAlias = _openapi.OpenAPIFailureInfo


ContinueAsNewResult: TypeAlias = _openapi.OpenAPIContinueAsNewResult


TaskResult: TypeAlias = _openapi.OpenAPITaskResult


Task: TypeAlias = _openapi.OpenAPITask


TaskEvent: TypeAlias = _openapi.OpenAPITaskEvent


TaskEventInput: TypeAlias = _openapi.OpenAPITaskEventInput


TaskEventPage: TypeAlias = _openapi.OpenAPITaskEventPage


EnqueueTaskRequest: TypeAlias = _openapi.OpenAPIEnqueueTaskRequest


class ActivityTaskPayload(TypedDict, total=False):
    activityType: str
    args: list[Any]
    workflowId: str
    workflowRunId: str
    workflowTaskId: str
    attempt: int
    cancellationType: str
    retry: "RetryPolicy"


RetryPolicy: TypeAlias = _openapi.OpenAPIRetryPolicy


ScheduleCalendarSpec: TypeAlias = _openapi.OpenAPIScheduleCalendarSpec


ScheduleSpec: TypeAlias = _openapi.OpenAPIScheduleSpec


ScheduleAction: TypeAlias = _openapi.OpenAPIScheduleAction


Schedule: TypeAlias = _openapi.OpenAPISchedule


CreateScheduleRequest: TypeAlias = _openapi.OpenAPICreateScheduleRequest


UpdateScheduleRequest: TypeAlias = _openapi.OpenAPIUpdateScheduleRequest


PauseScheduleRequest: TypeAlias = _openapi.OpenAPIPauseScheduleRequest


UnpauseScheduleRequest: TypeAlias = _openapi.OpenAPIUnpauseScheduleRequest


TriggerScheduleRequest: TypeAlias = _openapi.OpenAPITriggerScheduleRequest


TriggerScheduleResponse: TypeAlias = _openapi.OpenAPITriggerScheduleResponse


BackfillScheduleRequest: TypeAlias = _openapi.OpenAPIBackfillScheduleRequest


BackfillScheduleResponse: TypeAlias = _openapi.OpenAPIBackfillScheduleResponse


PollTaskResponse: TypeAlias = _openapi.OpenAPIPollTaskResponse


AgentPollDirective: TypeAlias = _openapi.OpenAPIAgentPollDirective


class AgentUpgradeRequest(TypedDict, total=False):
    image: str
    expectedVersion: int


class ShellExecPayload(TypedDict, total=False):
    """Payload for ``shell.exec`` tasks.

    ``secret_env`` maps an environment variable to a secret name in the
    agent's local secret store (``/run/secrets`` on the agent host). The
    agent resolves values when the task runs, so only names reach the control
    plane. Put credentials there, never in ``env``: plaintext
    credential-shaped keys are refused.
    """

    command: str
    args: list[str]
    env: dict[str, str]
    secret_env: dict[str, str]
    working_dir: str
    timeout_seconds: int


class ContainerExecPayload(TypedDict, total=False):
    """Payload for ``container.exec`` tasks.

    The Go agent runs a per-task container from ``image`` via its docker
    CLI (proxied through the worker stack's docker socket proxy). Useful
    for polyglot runtimes (Node, Bun, Python, Go, anything in an image)
    without baking those runtimes into the agent image itself.

    ``image`` is required. ``command``, when set, overrides the image's
    ENTRYPOINT; ``args`` becomes the container's CMD. ``pull_policy``
    mirrors ``docker run --pull`` (``always`` | ``missing`` | ``never``);
    omit for the default ``missing``. Env keys flow through the agent's
    allowlist — ``DOCKER_*``, ``POSTGRIP_*``, and host loader/interpreter
    prefixes are rejected.

    The agent runs the container with ``--rm --network=none`` and never
    mounts host paths; share state via stdin/args/env.
    """

    image: str
    command: str
    args: list[str]
    env: dict[str, str]
    secret_env: dict[str, str]
    working_dir: str
    pull_policy: str
    timeout_seconds: int


class WorkflowUIMetadata(TypedDict, total=False):
    displayName: str
    description: str
    details: dict[str, str | int | float | bool]
    tags: list[str]


class WorkflowStartOptions(TypedDict, total=False):
    namespace: str
    workflow_id: str
    workflow_id_reuse_policy: WorkflowIdReusePolicy
    task_queue: str
    args: list[Any]
    lease_timeout_seconds: int
    workflow_run_timeout_ms: int
    retry: RetryPolicy
    memo: dict[str, Any]
    search_attributes: dict[str, Any]
    ui: WorkflowUIMetadata


class ContinueAsNewOptions(TypedDict, total=False):
    workflow_id: str
    workflow_type: str
    task_queue: str
    args: list[Any]
    lease_timeout_seconds: int
    workflow_run_timeout_ms: int
    retry: RetryPolicy


class ChildWorkflowOptions(TypedDict, total=False):
    workflow_id: str
    task_queue: str
    args: list[Any]
    lease_timeout_seconds: int
    workflow_run_timeout_ms: int
    cancellation_type: CancellationType
    cancellation_scope: CancellationScopeType
    retry: RetryPolicy


class WorkflowExecutionDescription(TypedDict, total=False):
    workflowId: str
    runId: str
    taskId: str
    namespace: str
    taskQueue: str
    workflowType: str
    status: str
    attempt: int
    leaseTimeoutSeconds: int
    workflowRunTimeoutMs: int
    retry: RetryPolicy
    memo: dict[str, Any]
    searchAttributes: dict[str, Any]
    result: Any
    error: str
    startedAt: str
    updatedAt: str


WorkflowExecution: TypeAlias = _openapi.OpenAPIWorkflowExecution


WorkflowHistoryEvent: TypeAlias = _openapi.OpenAPIWorkflowHistoryEvent


WorkflowHistoryPage: TypeAlias = _openapi.OpenAPIWorkflowHistoryPage


WorkflowCountResponse: TypeAlias = _openapi.OpenAPIWorkflowCountResponse


Namespace: TypeAlias = _openapi.OpenAPINamespace


class WorkflowSignalDefinition(TypedDict):
    name: str
    type: Literal["signal"]
    args: list[Any]


class WorkflowQueryDefinition(TypedDict):
    name: str
    type: Literal["query"]
    args: list[Any]
    result: Any


class WorkflowUpdateDefinition(TypedDict):
    name: str
    type: Literal["update"]
    args: list[Any]
    result: Any


SignalWorkflowRequest: TypeAlias = _openapi.OpenAPISignalWorkflowRequest


SignalWithStartWorkflowRequest: TypeAlias = _openapi.OpenAPISignalWithStartWorkflowRequest


SignalWithStartWorkflowResponse: TypeAlias = _openapi.OpenAPISignalWithStartWorkflowResponse


CancelWorkflowRequest: TypeAlias = _openapi.OpenAPICancelWorkflowRequest


TerminateWorkflowRequest: TypeAlias = _openapi.OpenAPITerminateWorkflowRequest


class WorkflowQueryPayload(TypedDict):
    workflowId: str
    workflowType: str
    queryName: str
    args: list[Any]
    workflowRunId: NotRequired[str]


class WorkflowUpdatePayload(TypedDict):
    workflowId: str
    workflowType: str
    updateName: str
    args: list[Any]
    workflowRunId: NotRequired[str]


class WorkflowPayload(TypedDict, total=False):
    namespace: str
    workflowType: str
    workflowId: str
    runId: str
    workflowIdReusePolicy: WorkflowIdReusePolicy
    parentWorkflowId: str
    parentWorkflowRunId: str
    parentWorkflowTaskId: str
    parentCancellationType: CancellationType
    continuedFromWorkflowId: str
    runTimeoutMs: int
    retry: RetryPolicy
    memo: dict[str, Any]
    searchAttributes: dict[str, Any]
    args: list[Any]


class ActivityInvocationPayload(TypedDict, total=False):
    activityType: str
    workflowId: str
    workflowRunId: str
    workflowTaskId: str
    attempt: int
    cancellationType: CancellationType
    retry: RetryPolicy
    args: list[Any]


class WorkflowRuntimePayload(TypedDict, total=False):
    runtime_id: str
    image: str
    command: str
    args: list[str]
    env: dict[str, str]
    working_dir: str
    namespace: str
    queue: str
    pull_policy: str
    timeout_seconds: int
    # Isolation floor this workload requires; absent means the container
    # default. Requires ``image`` — a command-only runtime executes directly
    # on the agent host, which honors no isolation floor, and the
    # orchestrator rejects that combination at enqueue.
    isolation: IsolationTier


class TimerPayload(TypedDict):
    timerId: str
    durationMs: int
    fireAt: str
    workflowId: NotRequired[str]
    workflowRunId: NotRequired[str]
    workflowTaskId: NotRequired[str]


class ActivityOptions(TypedDict, total=False):
    start_to_close_timeout_ms: int
    schedule_to_close_timeout_ms: int
    cancellation_type: CancellationType
    cancellation_scope: CancellationScopeType
    retry: RetryPolicy


# --- sandbox platform ------------------------------------------------------
#
# Mirrors agent-sdk-protocol/sandbox.go. Timestamps are RFC3339 strings, as
# everywhere else in this module.

SandboxBackend: TypeAlias = _openapi.OpenAPISandboxBackend
SandboxDesiredState: TypeAlias = _openapi.OpenAPISandboxDesiredState
# Only "running", "stopped", "deleted" and "failed" are reported by agents
# today, and "scheduling" is written by the control plane at placement. The
# rest exist for forward compatibility — treat an unexpected value as
# in-flight rather than as an error.
SandboxObservedState: TypeAlias = _openapi.OpenAPISandboxObservedState
SandboxSessionKind: TypeAlias = _openapi.OpenAPISandboxSessionKind


SandboxResourceLimits: TypeAlias = _openapi.OpenAPISandboxResourceLimits


SandboxPortMapping: TypeAlias = _openapi.OpenAPISandboxPortMapping


SandboxNetworkPolicy: TypeAlias = _openapi.OpenAPISandboxNetworkPolicy


Sandbox: TypeAlias = _openapi.OpenAPISandbox


SandboxCreateRequest: TypeAlias = _openapi.OpenAPISandboxCreateRequest


SandboxListResponse: TypeAlias = _openapi.OpenAPISandboxListResponse


SandboxWorkspace: TypeAlias = _openapi.OpenAPISandboxWorkspace


SandboxWorkspaceListResponse: TypeAlias = _openapi.OpenAPISandboxWorkspaceListResponse


CreateSandboxSessionRequest: TypeAlias = _openapi.OpenAPICreateSandboxSessionRequest


CreateSandboxSessionResponse: TypeAlias = _openapi.OpenAPICreateSandboxSessionResponse


# --- convenience keyword options --------------------------------------------
#
# Each TypedDict below lists exactly the keywords one Agent convenience method
# accepts through ``**options`` and forwards to a consumer that uses them. They
# are static shapes for ``typing.Unpack``; the methods do not validate them.


class ConnectionOptions(TypedDict, total=False):
    """Keyword options ``Connection.connect`` and ``Client.connect`` forward to
    the ``Connection`` constructor."""

    timeout: float
    headers: dict[str, str] | None
    auth_token: str | None
    insecure_development: bool
    agent_id: str | None
    worker_id: str | None
    agent_name: str | None
    agent_host: str | None
    agent_namespace: str
    agent_queue: str
    agent_access_token: str | None
    agent_refresh_token: str | None
    agent_access_expires_at: str | _datetime | None
    agent_signing_private_key: str | None
    enable_retries: bool


class ListTasksOptions(TypedDict, total=False):
    """``Connection.list_tasks`` query options; ``None`` values are omitted."""

    namespace: str | None
    queue: str | None
    type: str | None
    state: TaskState | None
    order_by: str | None
    page_token: str | None
    limit: int | None
    offset: int | None


class ListSchedulesOptions(TypedDict, total=False):
    """``Connection.list_schedules`` and ``ScheduleClient.list`` query options;
    ``None`` values are omitted."""

    namespace: str | None
    state: ScheduleState | None
    page_token: str | None
    limit: int | None
    offset: int | None


class CountWorkflowsOptions(TypedDict, total=False):
    """``Connection.count_workflows`` query options; ``None`` values are
    omitted and ``search_attributes`` become ``search.<key>`` filters."""

    namespace: str | None
    id: str | None
    run_id: str | None
    type: str | None
    queue: str | None
    state: WorkflowState | None
    query: str | None
    q: str | None
    agent_id: str | None
    search_attributes: Mapping[str, JsonValue] | None


class ListWorkflowsOptions(CountWorkflowsOptions, total=False):
    """``Connection.list_workflows`` query options: the count filters plus
    ordering and paging."""

    order_by: str | None
    order: str | None
    page_token: str | None
    limit: int | None
    offset: int | None


class WorkflowCountOptions(CountWorkflowsOptions, total=False):
    """``WorkflowClient.count`` options: the count filters plus the
    Temporal-style ``workflow_id``, ``workflow_type`` and ``task_queue``
    spellings of ``id``, ``type`` and ``queue``."""

    workflow_id: str | None
    workflow_type: str | None
    task_queue: str | None


class WorkflowListOptions(ListWorkflowsOptions, total=False):
    """``WorkflowClient.list`` options: the list filters plus the
    Temporal-style ``workflow_id``, ``workflow_type`` and ``task_queue``
    spellings of ``id``, ``type`` and ``queue``."""

    workflow_id: str | None
    workflow_type: str | None
    task_queue: str | None


class WorkflowClientStartOptions(TypedDict, total=False):
    """Extra keyword options of ``WorkflowClient.start`` and
    ``WorkflowClient.signal_with_start``, beside their named parameters.

    ``workflow_run_timeout`` (a ``timedelta`` or seconds) takes precedence over
    ``workflow_run_timeout_ms``. ``ui`` is stored in the memo under
    ``postgrip.ui``.
    """

    workflow_id_reuse_policy: WorkflowIdReusePolicy | None
    workflow_run_timeout: _timedelta | float | None
    workflow_run_timeout_ms: int | None
    lease_timeout_seconds: int
    retry: RetryPolicy | None
    memo: dict[str, JsonValue] | None
    search_attributes: dict[str, JsonValue] | None
    ui: WorkflowUIMetadata | None


class WorkflowClientExecuteOptions(WorkflowClientStartOptions, total=False):
    """``WorkflowClient.execute`` options: every ``WorkflowClient.start``
    keyword plus the result-wait ``timeout`` in seconds."""

    workflow_id: str | None
    task_queue: str
    namespace: str
    args: list[Any] | None
    timeout: float | None


class ClientStartWorkflowOptions(WorkflowClientStartOptions, total=False):
    """``Client.start_workflow`` options. ``id`` is the Temporal-style alias of
    ``workflow_id``; workflow arguments are positional."""

    id: str
    workflow_id: str | None
    task_queue: str
    namespace: str


class ClientExecuteWorkflowOptions(ClientStartWorkflowOptions, total=False):
    """``Client.execute_workflow`` options: the start options plus the
    result-wait ``timeout`` in seconds."""

    timeout: float | None


# Computed last, deliberately. It used to sit above the sandbox section, and a
# `globals()` comprehension only sees what has already been defined — so every
# sandbox type was silently absent from `from postgrip.agent.types import *`,
# unlike every other public type in this module. Keep new declarations above
# this line.
__all__ = [name for name in globals() if not name.startswith("_")]
