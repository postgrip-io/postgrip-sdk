from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import AsyncIterator, Callable
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
from ._workflow_models import (
    _definition_name,
    _duration_ms,
    _memo_with_workflow_ui,
    _normalize_temporal_start_options,
    _workflow_query_options,
    _workflow_result_step,
)


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

    def signal_with_start(self, workflow: Callable[..., Any] | str, *, signal: str | Any, signal_args: list[Any] | None = None, workflow_id: str | None = None, task_queue: str = "default", namespace: str = "default", args: list[Any] | None = None, idempotency_key: str | None = None, **options: Unpack[WorkflowClientStartOptions]) -> "WorkflowHandle":
        """Signal the workflow's running execution, starting one first when none
        runs. An ``idempotency_key`` makes a resend after a lost answer return the
        first request's result instead of signalling again or starting another run."""
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
        }, idempotency_key=idempotency_key)
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

    async def signal(self, name: str | Any, *args: Any, idempotency_key: str | None = None) -> None:
        """Signal the workflow. An ``idempotency_key`` makes a resend after a lost
        answer return the first signal instead of appending another."""
        await run_cancellable(self.signal_sync, name, *args, idempotency_key=idempotency_key)

    def signal_sync(self, name: str | Any, *args: Any, idempotency_key: str | None = None) -> None:
        signal_name = _definition_name(name)
        self.connection.signal_workflow(self.run_id or self.workflow_id, signal_name, list(args), idempotency_key=idempotency_key)

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

    def enqueue(self, *, type: str, namespace: str = "default", queue: str = "default", payload: JsonValue = None, lease_timeout_seconds: int = 0, idempotency_key: str | None = None) -> Task:
        """Send a task. An ``idempotency_key`` makes a resend after a lost answer
        return the first task instead of enqueueing another."""
        return self.connection.enqueue_task({
            "namespace": namespace,
            "queue": queue,
            "type": type,
            "payload": payload,
            "lease_timeout_seconds": lease_timeout_seconds,
        }, idempotency_key=idempotency_key)

    def cancel(self, task_id: str, *, reason: str | None = None) -> Task:
        """End a task that has not finished; see ``Connection.cancel_task``."""
        return self.connection.cancel_task(task_id, reason)

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
