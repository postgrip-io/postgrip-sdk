from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Unpack

from .._internal.http import run_cancellable
from .errors import TaskFailedError, TimeoutFailure
from .sandbox import SandboxClient
from .types import (
    BackfillScheduleRequest,
    BackfillScheduleResponse,
    ClientExecuteWorkflowOptions,
    ClientStartWorkflowOptions,
    ConnectionOptions,
    CreateScheduleRequest,
    IsolationTier,
    JsonValue,
    ListSchedulesOptions,
    PauseScheduleRequest,
    RetryPolicy,
    Schedule,
    ScheduleCalendarSpec,
    ScheduleMissedRunPolicy,
    ScheduleOverlapPolicy,
    Task,
    TaskEvent,
    TriggerScheduleRequest,
    TriggerScheduleResponse,
    UnpauseScheduleRequest,
    UpdateScheduleRequest,
    WorkflowClientExecuteOptions,
    WorkflowClientStartOptions,
    WorkflowCountOptions,
    WorkflowExecution,
    WorkflowHistoryEvent,
    WorkflowIdReusePolicy,
    WorkflowListOptions,
    WorkflowUIMetadata,
)
from .workflow import workflow_name

# Compatibility re-exports: these names were defined here before the Connection
# adapter moved to _connection.py, and existing callers and tests import them.
from .._internal.http import has_authorization_header  # noqa: F401
from ._connection import (  # noqa: F401
    DEFAULT_ADDRESS,
    Connection,
    _Missing,
    _parse_timestamp,
    urlopen,
)

_POSTGRIP_UI_MEMO_KEY = "postgrip.ui"











class Client:
    def __init__(self, connection: Connection | None = None):
        self.connection = connection or Connection()
        self.workflow = WorkflowClient(self.connection)
        self.task = TaskClient(self.connection)
        self.schedule = ScheduleClient(self.connection)
        self.sandbox = SandboxClient(self.connection)

    @classmethod
    async def connect(cls, address: str | None = None, **options: Unpack[ConnectionOptions]) -> "Client":
        return cls(await Connection.connect(address, **options))

    async def start_workflow(self, workflow: Callable[..., Any] | str, *args: Any, **options: Unpack[ClientStartWorkflowOptions]) -> "WorkflowHandle":
        return await run_cancellable(self.workflow.start, workflow, args=list(args), **_normalize_temporal_start_options(options))

    async def execute_workflow(self, workflow: Callable[..., Any] | str, *args: Any, **options: Unpack[ClientExecuteWorkflowOptions]) -> Any:
        timeout = options.pop("timeout", None)
        handle = await self.start_workflow(workflow, *args, **options)
        return await handle.result(timeout=timeout)

    def get_workflow_handle(self, workflow_id: str, *, run_id: str | None = None, workflow_type: str = "unknown") -> "WorkflowHandle":
        return self.workflow.get_handle(workflow_id, run_id=run_id, workflow_type=workflow_type)


class WorkflowClient:
    def __init__(self, connection: Connection):
        self.connection = connection

    def start(self, workflow: Callable[..., Any] | str, *, workflow_id: str | None = None, task_queue: str = "default", namespace: str = "default", args: list[Any] | None = None, **options: Unpack[WorkflowClientStartOptions]) -> "WorkflowHandle":
        workflow_type = workflow_name(workflow)
        if not workflow_type:
            raise ValueError("workflow type is required")
        workflow_id = workflow_id or str(uuid.uuid4())
        task = self.connection.enqueue_task({
            "namespace": namespace,
            "queue": task_queue,
            "type": f"workflow:{workflow_type}",
            "payload": {
                "namespace": namespace,
                "workflowType": workflow_type,
                "workflowId": workflow_id,
                "workflowIdReusePolicy": options.get("workflow_id_reuse_policy"),
                "runTimeoutMs": _duration_ms(options.get("workflow_run_timeout") or options.get("workflow_run_timeout_ms")),
                "retry": options.get("retry"),
                "memo": _memo_with_workflow_ui(options.get("memo"), options.get("ui")),
                "searchAttributes": options.get("search_attributes"),
                "args": args or [],
            },
            "lease_timeout_seconds": options.get("lease_timeout_seconds", 0),
        })
        return WorkflowHandle(self.connection, workflow_id, workflow_type, task_id=task["id"], run_id=(task.get("payload") or {}).get("runId"))

    def execute(self, workflow: Callable[..., Any] | str, **options: Unpack[WorkflowClientExecuteOptions]) -> Any:
        timeout = options.pop("timeout", None)
        return self.start(workflow, **options).result_sync(timeout=timeout)

    def signal_with_start(self, workflow: Callable[..., Any] | str, *, signal: str | Any, signal_args: list[Any] | None = None, workflow_id: str | None = None, task_queue: str = "default", namespace: str = "default", args: list[Any] | None = None, **options: Unpack[WorkflowClientStartOptions]) -> "WorkflowHandle":
        workflow_type = workflow_name(workflow)
        if not workflow_type:
            raise ValueError("workflow type is required")
        workflow_id = workflow_id or str(uuid.uuid4())
        signal_name = _definition_name(signal)
        response = self.connection.signal_with_start_workflow(workflow_id, {
            "namespace": namespace,
            "queue": task_queue,
            "workflowType": workflow_type,
            "workflowId": workflow_id,
            "workflowIdReusePolicy": options.get("workflow_id_reuse_policy"),
            "lease_timeout_seconds": options.get("lease_timeout_seconds", 0),
            "runTimeoutMs": _duration_ms(options.get("workflow_run_timeout") or options.get("workflow_run_timeout_ms")),
            "retry": options.get("retry"),
            "memo": _memo_with_workflow_ui(options.get("memo"), options.get("ui")),
            "searchAttributes": options.get("search_attributes"),
            "args": args or [],
            "signal": {"name": signal_name, "args": signal_args or []},
        })
        workflow_result = response["workflow"]
        return WorkflowHandle(
            self.connection,
            workflow_result["id"],
            workflow_result["type"],
            task_id=response["task"]["id"],
            run_id=workflow_result.get("run_id"),
        )

    def get_handle(self, workflow_id: str, *, run_id: str | None = None, workflow_type: str = "unknown") -> "WorkflowHandle":
        return WorkflowHandle(self.connection, workflow_id, workflow_type, run_id=run_id)

    def list(self, **options: Unpack[WorkflowListOptions]) -> list[WorkflowExecution]:
        return self.connection.list_workflows(**_workflow_query_options(options))

    def count(self, **options: Unpack[WorkflowCountOptions]) -> int:
        return self.connection.count_workflows(**_workflow_query_options(options))


@dataclass
class WorkflowHandle:
    connection: Connection
    workflow_id: str
    workflow_type: str = "unknown"
    task_id: str | None = None
    run_id: str | None = None

    async def describe(self) -> WorkflowExecution:
        return await run_cancellable(self.describe_sync)

    def describe_sync(self) -> WorkflowExecution:
        workflow = self.connection.get_workflow(self.run_id or self.workflow_id)
        self.task_id = workflow["task_id"]
        self.run_id = workflow.get("run_id")
        self.workflow_type = workflow["type"]
        return workflow

    async def result(self, *, timeout: float | None = None, poll_interval: float = 1) -> Any:
        started = time.time()
        task_id = self.task_id or (await self.describe())["task_id"]
        while True:
            task = await run_cancellable(self.connection.get_task, task_id)
            step = _workflow_result_step(task, task_id)
            if step.resolve:
                workflow = await run_cancellable(self.connection.get_workflow, self.run_id or self.workflow_id)
                step = _workflow_result_step(task, task_id, workflow)
            if step.done:
                return step.value
            if step.next_task_id is not None:
                task_id = self.task_id = step.next_task_id
                continue
            self._check_result_timeout(started, timeout)
            await asyncio.sleep(poll_interval)

    def result_sync(self, *, timeout: float | None = None, poll_interval: float = 1) -> Any:
        started = time.time()
        task_id = self.task_id or self.describe_sync()["task_id"]
        while True:
            task = self.connection.get_task(task_id)
            step = _workflow_result_step(task, task_id)
            if step.resolve:
                workflow = self.connection.get_workflow(self.run_id or self.workflow_id)
                step = _workflow_result_step(task, task_id, workflow)
            if step.done:
                return step.value
            if step.next_task_id is not None:
                task_id = self.task_id = step.next_task_id
                continue
            self._check_result_timeout(started, timeout)
            time.sleep(poll_interval)

    def _check_result_timeout(self, started: float, timeout: float | None) -> None:
        if timeout is not None and time.time() - started > timeout:
            raise TimeoutFailure(f"workflow {self.workflow_id} timed out")

    async def history(self) -> list[WorkflowHistoryEvent]:
        return await run_cancellable(self.history_sync)

    def history_sync(self) -> list[WorkflowHistoryEvent]:
        return self.connection.get_workflow_history(self.run_id or self.workflow_id)

    async def events(self) -> list[TaskEvent]:
        task_id = self.task_id or (await self.describe())["task_id"]
        return await run_cancellable(self.connection.get_task_events, task_id)

    async def watch_events(self, *, poll_interval: float = 1) -> AsyncIterator[TaskEvent]:
        task_id = self.task_id or (await self.describe())["task_id"]
        async for event in _watch_task_events(self.connection, task_id, poll_interval=poll_interval):
            yield event

    async def signal(self, name: str | Any, *args: Any) -> None:
        await run_cancellable(self.signal_sync, name, *args)

    def signal_sync(self, name: str | Any, *args: Any) -> None:
        signal_name = _definition_name(name)
        self.connection.signal_workflow(self.run_id or self.workflow_id, signal_name, list(args))

    async def cancel(self, reason: str | None = None) -> None:
        await run_cancellable(self.connection.cancel_workflow, self.run_id or self.workflow_id, reason)

    async def terminate(self, reason: str | None = None) -> None:
        await run_cancellable(self.connection.terminate_workflow, self.run_id or self.workflow_id, reason)

    async def query(self, name: str | Any, *args: Any, timeout: float | None = None) -> Any:
        query_name = _definition_name(name)
        workflow = await self.describe()
        task = await run_cancellable(self.connection.enqueue_task, {
            "namespace": workflow["namespace"],
            "queue": workflow["queue"],
            "type": f"query:{workflow['type']}",
            "payload": {
                "workflowId": workflow["id"],
                "workflowRunId": workflow.get("run_id"),
                "workflowType": workflow["type"],
                "queryName": query_name,
                "args": list(args),
            },
        })
        return await _wait_for_task(self.connection, task["id"], timeout=timeout, failure_message="workflow query failed")

    async def execute_update(self, name: str | Any, *args: Any, timeout: float | None = None) -> Any:
        handle = await self.start_update(name, *args)
        return await handle.result(timeout=timeout)

    async def start_update(self, name: str | Any, *args: Any) -> "WorkflowUpdateHandle":
        update_name = _definition_name(name)
        workflow = await self.describe()
        task = await run_cancellable(self.connection.enqueue_task, {
            "namespace": workflow["namespace"],
            "queue": workflow["queue"],
            "type": f"update:{workflow['type']}",
            "payload": {
                "workflowId": workflow["id"],
                "workflowRunId": workflow.get("run_id"),
                "workflowType": workflow["type"],
                "updateName": update_name,
                "args": list(args),
            },
        })
        return WorkflowUpdateHandle(self.connection, task["id"])


@dataclass
class WorkflowUpdateHandle:
    connection: Connection
    update_id: str

    async def result(self, *, timeout: float | None = None, poll_interval: float = 0.05) -> Any:
        return await _wait_for_task(self.connection, self.update_id, timeout=timeout, poll_interval=poll_interval, failure_message="workflow update failed")

    async def events(self) -> list[TaskEvent]:
        return await run_cancellable(self.connection.get_task_events, self.update_id)

    async def watch_events(self, *, poll_interval: float = 1) -> AsyncIterator[TaskEvent]:
        async for event in _watch_task_events(self.connection, self.update_id, poll_interval=poll_interval):
            yield event


class TaskClient:
    def __init__(self, connection: Connection):
        self.connection = connection

    def enqueue(self, *, type: str, namespace: str = "default", queue: str = "default", payload: JsonValue = None, lease_timeout_seconds: int = 0) -> Task:
        return self.connection.enqueue_task({
            "namespace": namespace,
            "queue": queue,
            "type": type,
            "payload": payload,
            "lease_timeout_seconds": lease_timeout_seconds,
        })

    def shell_exec(self, *, command: str, args: list[str] | None = None, env: dict[str, str] | None = None, working_dir: str | None = None, timeout_seconds: int | None = None, queue: str = "default", namespace: str = "default") -> Task:
        return self.enqueue(
            namespace=namespace,
            queue=queue,
            type="shell.exec",
            payload={
                "command": command,
                "args": args or [],
                "env": env or {},
                "working_dir": working_dir,
                "timeout_seconds": timeout_seconds,
            },
        )

    def container_exec(
        self,
        *,
        image: str,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
        pull_policy: str | None = None,
        timeout_seconds: int | None = None,
        queue: str = "default",
        namespace: str = "default",
    ) -> Task:
        """Enqueue a ``container.exec`` task.

        Mirrors :meth:`shell_exec` but runs the command inside a per-task
        container that the Go agent launches via its docker CLI. Requires
        the agent to be on the docker socket proxy network (DOCKER_HOST
        set on the agent process).
        """
        # Drop None fields so the agent's payload sees absent keys instead
        # of explicit nulls — pull_policy default is server-side ("missing"),
        # and command/working_dir absence means "use the image defaults".
        payload: dict[str, Any] = {"image": image}
        if command is not None:
            payload["command"] = command
        if args is not None:
            payload["args"] = args
        if env is not None:
            payload["env"] = env
        if working_dir is not None:
            payload["working_dir"] = working_dir
        if pull_policy is not None:
            payload["pull_policy"] = pull_policy
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        return self.enqueue(
            namespace=namespace,
            queue=queue,
            type="container.exec",
            payload=payload,
        )

    def workflow_runtime(
        self,
        *,
        command: str | None = None,
        image: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
        pull_policy: str | None = None,
        timeout_seconds: int | None = None,
        isolation: IsolationTier | None = None,
        queue: str = "default",
        namespace: str = "default",
        runtime_queue: str | None = None,
        runtime_namespace: str | None = None,
        runtime_id: str | None = None,
        lease_timeout_seconds: int = 0,
    ) -> Task:
        """Enqueue a managed SDK runtime on an existing host-agent pool.

        ``isolation`` is the isolation floor the workload requires, one of
        ``"container"`` (the default) or ``"microvm"``. It is a floor, not an
        exact match: container work may be scheduled onto a stronger tier,
        microvm work is never downgraded. It requires ``image`` — the
        orchestrator rejects an isolation floor on a command-only runtime,
        which would execute directly on the agent host honoring no floor.
        """
        payload: dict[str, Any] = {}
        if image is not None:
            payload["image"] = image
        if command is not None:
            payload["command"] = command
        if args is not None:
            payload["args"] = args
        if env is not None:
            payload["env"] = env
        if working_dir is not None:
            payload["working_dir"] = working_dir
        if pull_policy is not None:
            payload["pull_policy"] = pull_policy
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        if isolation is not None:
            payload["isolation"] = isolation
        payload["queue"] = runtime_queue or f"postgrip-runtime-{uuid.uuid4().hex[:16]}"
        if runtime_namespace is not None:
            payload["namespace"] = runtime_namespace
        if runtime_id is not None:
            payload["runtime_id"] = runtime_id
        return self.enqueue(
            namespace=namespace,
            queue=queue,
            type="workflow.runtime",
            payload=payload,
            lease_timeout_seconds=lease_timeout_seconds,
        )

    def noop(self, *, queue: str = "default", namespace: str = "default") -> Task:
        return self.enqueue(namespace=namespace, queue=queue, type="noop")

    def events(self, task_id: str) -> list[TaskEvent]:
        return self.connection.get_task_events(task_id)

    async def watch_events(self, task_id: str, *, poll_interval: float = 1) -> AsyncIterator[TaskEvent]:
        async for event in _watch_task_events(self.connection, task_id, poll_interval=poll_interval):
            yield event


class ScheduleClient:
    def __init__(self, connection: Connection):
        self.connection = connection

    def create(self, request: CreateScheduleRequest) -> Schedule:
        return self.connection.create_schedule(request)

    def create_workflow_schedule(self, *, workflow: Callable[..., Any] | str, schedule_id: str | None = None, namespace: str = "default", task_queue: str = "default", args: list[Any] | None = None, interval_seconds: int | None = None, cron: str | None = None, calendar: ScheduleCalendarSpec | None = None, timezone: str | None = None, jitter_seconds: int | None = None, catch_up_window_seconds: int | None = None, missed_run_policy: ScheduleMissedRunPolicy | None = None, start_at: datetime | str | None = None, workflow_id: str | None = None, workflow_id_reuse_policy: WorkflowIdReusePolicy | None = None, overlap_policy: ScheduleOverlapPolicy | None = None, workflow_run_timeout_ms: int | None = None, retry: RetryPolicy | None = None, memo: dict[str, JsonValue] | None = None, search_attributes: dict[str, JsonValue] | None = None, ui: WorkflowUIMetadata | None = None) -> Schedule:
        workflow_type = workflow_name(workflow)
        if isinstance(start_at, datetime):
            start_at = start_at.isoformat()
        return self.create({
            "id": schedule_id,
            "namespace": namespace,
            "overlap_policy": overlap_policy,
            "spec": {
                "interval_seconds": interval_seconds,
                "cron": cron,
                "calendar": calendar,
                "timezone": timezone,
                "jitter_seconds": jitter_seconds,
                "catch_up_window_seconds": catch_up_window_seconds,
                "missed_run_policy": missed_run_policy,
                "start_at": start_at,
            },
            "action": {
                "namespace": namespace,
                "queue": task_queue,
                "workflowType": workflow_type,
                "workflowId": workflow_id,
                "workflowIdReusePolicy": workflow_id_reuse_policy,
                "runTimeoutMs": workflow_run_timeout_ms,
                "retry": retry,
                "memo": _memo_with_workflow_ui(memo, ui),
                "searchAttributes": search_attributes,
                "args": args or [],
            },
        })

    def list(self, **options: Unpack[ListSchedulesOptions]) -> list[Schedule]:
        return self.connection.list_schedules(**options)

    def get(self, schedule_id: str) -> Schedule:
        return self.connection.get_schedule(schedule_id)

    def update(self, schedule_id: str, request: UpdateScheduleRequest) -> Schedule:
        return self.connection.update_schedule(schedule_id, request)

    def delete(self, schedule_id: str) -> Schedule:
        return self.connection.delete_schedule(schedule_id)

    def pause(self, schedule_id: str, request: PauseScheduleRequest | None = None) -> Schedule:
        return self.connection.pause_schedule(schedule_id, request)

    def unpause(self, schedule_id: str, request: UnpauseScheduleRequest | None = None) -> Schedule:
        return self.connection.unpause_schedule(schedule_id, request)

    def trigger(self, schedule_id: str, request: TriggerScheduleRequest | None = None) -> TriggerScheduleResponse:
        return self.connection.trigger_schedule(schedule_id, request)

    def backfill(self, schedule_id: str, request: BackfillScheduleRequest) -> BackfillScheduleResponse:
        return self.connection.backfill_schedule(schedule_id, request)


@dataclass(frozen=True)
class _WorkflowResultStep:
    """What a workflow result wait does after reading one task snapshot."""

    done: bool = False
    value: Any = None
    next_task_id: str | None = None
    resolve: bool = False


def _workflow_result_step(
    task: Task,
    task_id: str,
    workflow: WorkflowExecution | None = None,
) -> _WorkflowResultStep:
    """Decide the next result-wait step; an empty step means keep waiting.

    A failed task needs the workflow's current run: pass *workflow* once the
    caller has read it after a ``resolve`` step.
    """
    if task["state"] == "succeeded":
        result = task.get("result") or {}
        next_task_id = (result.get("continue_as_new") or {}).get("task_id")
        if next_task_id:
            return _WorkflowResultStep(next_task_id=next_task_id)
        return _WorkflowResultStep(done=True, value=result.get("value"))
    if task["state"] == "failed":
        if workflow is None:
            return _WorkflowResultStep(resolve=True)
        if workflow["state"] == "running" and workflow["task_id"] != task_id:
            return _WorkflowResultStep(next_task_id=workflow["task_id"])
        raise TaskFailedError(task["id"], task.get("error") or "workflow failed")
    return _WorkflowResultStep()


async def _wait_for_task(connection: Connection, task_id: str, *, timeout: float | None, poll_interval: float = 0.05, failure_message: str) -> Any:
    started = time.time()
    while True:
        task = await run_cancellable(connection.get_task, task_id)
        if task["state"] == "succeeded":
            return (task.get("result") or {}).get("value")
        if task["state"] == "failed":
            raise TaskFailedError(task["id"], task.get("error") or failure_message)
        if timeout is not None and time.time() - started > timeout:
            raise TimeoutFailure(f"task {task_id} timed out")
        await asyncio.sleep(poll_interval)


async def _watch_task_events(connection: Connection, task_id: str, *, poll_interval: float) -> AsyncIterator[TaskEvent]:
    seen: set[str] = set()
    while True:
        events = await run_cancellable(connection.get_task_events, task_id)
        for event in events:
            event_id = str(event.get("id") or "")
            if event_id not in seen:
                seen.add(event_id)
                yield event
        task = await run_cancellable(connection.get_task, task_id)
        if task["state"] in {"succeeded", "failed"}:
            return
        await asyncio.sleep(poll_interval)








def _workflow_query_options(options: Mapping[str, Any]) -> dict[str, Any]:
    mapping = {
        "workflow_id": "id",
        "run_id": "run_id",
        "workflow_type": "type",
        "task_queue": "queue",
        "order_by": "order_by",
        "page_token": "page_token",
        "search_attributes": "search_attributes",
    }
    return {mapping.get(key, key): value for key, value in options.items() if value is not None}


def _memo_with_workflow_ui(memo: Mapping[str, Any] | None, ui: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not ui:
        return memo
    ui_memo = _workflow_ui_memo(ui)
    if not ui_memo:
        return memo
    return {**(memo or {}), _POSTGRIP_UI_MEMO_KEY: ui_memo}


def _workflow_ui_memo(ui: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    display_name = _clean_string(ui.get("displayName") or ui.get("display_name"))
    if display_name:
        out["displayName"] = display_name
    description = _clean_string(ui.get("description"))
    if description:
        out["description"] = description
    details = ui.get("details")
    if isinstance(details, dict):
        clean_details = {str(key).strip(): value for key, value in details.items() if str(key).strip()}
        if clean_details:
            out["details"] = clean_details
    tags = ui.get("tags")
    if isinstance(tags, list):
        clean_tags = [_clean_string(tag) for tag in tags]
        clean_tags = [tag for tag in clean_tags if tag]
        if clean_tags:
            out["tags"] = clean_tags
    return out


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _normalize_temporal_start_options(options: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(options)
    if "id" in normalized and "workflow_id" not in normalized:
        normalized["workflow_id"] = normalized.pop("id")
    return normalized




def _definition_name(value: Any) -> str:
    return value if isinstance(value, str) else value.name


def _duration_ms(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds() * 1000)
    return int(value)
