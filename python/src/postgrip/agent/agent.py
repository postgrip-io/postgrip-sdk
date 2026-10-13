from __future__ import annotations

import asyncio
from collections.abc import Mapping
import inspect
import os
import threading
import time
import uuid
import weakref
from typing import Any, Awaitable, Callable, Iterable

from . import activity, workflow
from ._replay import DeterminismError, WorkflowReplay, ownership_candidates
from .client import Client, Connection
from .errors import ApplicationFailure, CancelledFailure, is_terminal_task_mutation

WORKFLOW_RUNTIME_TASK_TYPES = ["workflow:", "activity:", "query:", "update:"]


class Agent:
    def __init__(
        self,
        client: Client | Connection | None = None,
        *,
        connection: Connection | None = None,
        task_queue: str | None = None,
        workflows: dict[str, Callable[..., Any] | type] | Iterable[Callable[..., Any] | type],
        activities: dict[str, Callable[..., Any]] | Iterable[Callable[..., Any]] | None = None,
        namespace: str = "default",
        identity: str | None = None,
        name: str | None = None,
        host: str | None = None,
        poll_interval: float = 1,
        max_concurrent_tasks: int = 4,
    ):
        self.connection = _connection_from_client(client, connection)
        self.task_queue = task_queue or os.environ.get("POSTGRIP_AGENT_TASK_QUEUE")
        if not self.task_queue:
            raise TypeError("task_queue is required")
        self.workflows = _workflow_registry(workflows)
        self.activities = _activity_registry(activities or {})
        self.namespace = os.environ.get("POSTGRIP_AGENT_NAMESPACE", namespace) if namespace == "default" else namespace
        managed_runtime = os.environ.get("POSTGRIP_AGENT_MANAGED_RUNTIME") == "true"
        if not managed_runtime:
            raise RuntimeError("postgrip-agent: Agent workers must be launched by a PostGrip host agent as managed workflow runtimes; submit workflow.runtime work to an agent pool instead")
        self.identity = identity or os.environ.get("POSTGRIP_AGENT_ID") or f"py-agent-{uuid.uuid4()}"
        self.connection.configure_agent_auth(
            agent_id=self.identity,
            agent_name=name,
            agent_host=host,
            namespace=self.namespace,
            queue=self.task_queue,
            access_token=os.environ.get("POSTGRIP_AGENT_ACCESS_TOKEN"),
            refresh_token=os.environ.get("POSTGRIP_AGENT_REFRESH_TOKEN"),
            access_expires_at=os.environ.get("POSTGRIP_AGENT_ACCESS_EXPIRES_AT"),
            signing_private_key=os.environ.get("POSTGRIP_AGENT_SIGNING_PRIVATE_KEY"),
        )
        self.poll_interval = poll_interval
        self.max_concurrent_tasks = max(1, int(max_concurrent_tasks))
        self._stopping = False
        self._shutdown_timeout: float | None = None
        self._in_flight: set[asyncio.Task[None]] = set()
        # Per-invocation locks that schedule new commands one at a time, in call order.
        self._command_locks: weakref.WeakKeyDictionary[WorkflowReplay, _CommandScheduler] = weakref.WeakKeyDictionary()

    @classmethod
    async def create(cls, **options: Any) -> "Agent":
        agent = cls(**options)
        await asyncio.to_thread(agent.connection.health)
        return agent

    def shutdown(self, *, timeout: float | None = None) -> None:
        self._stopping = True
        self._shutdown_timeout = timeout

    async def run(self) -> None:
        try:
            while not self._stopping:
                self._reap_finished_tasks()
                if len(self._in_flight) >= self.max_concurrent_tasks:
                    await self._wait_for_task_slot()
                    continue
                try:
                    response = await asyncio.to_thread(
                        self.connection.poll_task_response,
                        namespace=self.namespace,
                        queue=self.task_queue,
                        agent_id=self.identity,
                        wait_seconds=max(1, int(self.poll_interval)),
                        task_types=WORKFLOW_RUNTIME_TASK_TYPES,
                    )
                except Exception as exc:
                    if self._stopping:
                        break
                    print(f"postgrip-agent: poll failed: {exc}", flush=True)
                    await asyncio.sleep(self.poll_interval)
                    continue
                directive = response.get("directive") or {}
                if directive.get("type") == "shutdown":
                    break
                task = response.get("task")
                if not task:
                    await asyncio.sleep(self.poll_interval)
                    continue
                self._start_task(task)
        finally:
            self._stopping = True
            await self._drain_in_flight(self._shutdown_timeout)

    def run_sync(self) -> None:
        asyncio.run(self.run())

    async def run_until(self, awaitable: Awaitable[Any]) -> Any:
        agent_task = asyncio.create_task(self.run())
        try:
            return await awaitable
        finally:
            self.shutdown()
            await agent_task

    async def _execute(self, task: dict[str, Any]) -> None:
        task_type = task["type"]
        if task_type.startswith("workflow:") or task_type.startswith("query:") or task_type.startswith("update:"):
            await self._with_lease_renewal(task, lambda: self._execute_workflow_family_task(task))
            return
        if task_type.startswith("activity:"):
            await self._with_lease_renewal(task, lambda: self._execute_activity_task(task))
            return
        await self._fail_task(task, f"task type {task_type} is not supported by the Python agent", ApplicationFailure.non_retryable_failure(f"task type {task_type} is not supported by the Python agent", "UnsupportedTaskType", task_type))

    async def _execute_workflow_family_task(self, task: dict[str, Any]) -> None:
        if task["type"].startswith("query:"):
            await self._execute_query_task(task)
            return
        if task["type"].startswith("update:"):
            await self._execute_update_task(task)
            return
        await self._execute_workflow_task(task)

    async def _execute_workflow_task(self, task: dict[str, Any]) -> None:
        started_at = _now()
        try:
            payload = task.get("payload") or {}
            workflow_type = payload.get("workflowType") or task["type"].removeprefix("workflow:")
            target = self.workflows.get(workflow_type)
            if target is None:
                raise ApplicationFailure.non_retryable_failure(f"workflow {workflow_type} is not registered", "WorkflowNotRegistered", workflow_type)
            workflow_id = payload.get("workflowId") or task["id"]
            workflow_run_id = payload.get("runId") or workflow_id
            history = await asyncio.to_thread(self.connection.get_workflow_history, workflow_run_id)
            replay = WorkflowReplay(history, await self._read_command_owners(history))
            handlers = WorkflowHandlers(replay)
            await self._emit(task["id"], "started", "workflow", f"started workflow {workflow_type}", {"workflowType": workflow_type})
            try:
                value = await self._run_workflow(target, task, payload, replay, handlers)
            except Exception as exc:
                # Nondeterminism is sticky: a recorded violation fails the task even
                # when workflow code caught it and then suspended, continued or raised.
                await self._drain_commands(replay)
                if isinstance(exc, workflow.ContinueAsNewCommand):
                    # Continuing as new is a completion too.
                    _check_body_consumed(replay)
                _raise_if_nondeterministic(replay)
                raise
            await self._drain_commands(replay)
            # A completing workflow must have replayed every command it recorded.
            _check_body_consumed(replay)
            await self._emit(task["id"], "completed", "workflow", f"completed workflow {workflow_type}")
            await self._complete_task(task, {
                "value": value,
                "message": "workflow completed",
                "started_at": started_at,
                "finished_at": _now(),
            })
        except WorkflowBlocked as exc:
            await self._block_task(task, str(exc))
        except workflow.ContinueAsNewCommand as exc:
            await self._complete_workflow_as_continued(task, exc, started_at)
        except Exception as exc:
            await self._emit(task["id"], "failed", "workflow", str(exc))
            await self._fail_task(task, str(exc), exc, started_at=started_at)

    async def _execute_query_task(self, task: dict[str, Any]) -> None:
        await self._execute_handler_task(task, "query")

    async def _execute_update_task(self, task: dict[str, Any]) -> None:
        await self._execute_handler_task(task, "update")

    async def _execute_handler_task(self, task: dict[str, Any], kind: str) -> None:
        started_at = _now()
        name_key = "queryName" if kind == "query" else "updateName"
        invalid_code = "InvalidWorkflowQueryPayload" if kind == "query" else "InvalidWorkflowUpdatePayload"
        missing_code = "QueryNotRegistered" if kind == "query" else "UpdateNotRegistered"
        try:
            payload_value = task.get("payload")
            if payload_value is None:
                payload: Mapping[str, Any] = {}
            elif isinstance(payload_value, Mapping):
                payload = payload_value
            else:
                raise ApplicationFailure.non_retryable_failure(f"invalid workflow {kind} payload", invalid_code)
            name = payload.get(name_key)
            workflow_type = payload.get("workflowType")
            if not payload.get("workflowId") or not workflow_type or not name:
                raise ApplicationFailure.non_retryable_failure(f"invalid workflow {kind} payload", invalid_code)
            target = self.workflows.get(workflow_type)
            if target is None:
                raise ApplicationFailure.non_retryable_failure(f"workflow {workflow_type} is not registered", "WorkflowNotRegistered", workflow_type)
            source_workflow = await asyncio.to_thread(self.connection.get_workflow, payload.get("workflowRunId") or payload["workflowId"])
            source_task = await asyncio.to_thread(self.connection.get_task, source_workflow["task_id"])
            history = await asyncio.to_thread(self.connection.get_workflow_history, payload.get("workflowRunId") or payload["workflowId"])
            replay = WorkflowReplay(history, await self._read_command_owners(history))
            handlers = WorkflowHandlers(replay)
            await self._emit(task["id"], "started", kind, f"started {kind} {name}", {"workflowType": workflow_type})
            try:
                await self._run_workflow(target, source_task, source_task.get("payload") or {}, replay, handlers, query_mode=True)
            except WorkflowQueryReady:
                pass
            except Exception:
                # Nondeterminism is sticky on every exit from interaction replay.
                _raise_if_nondeterministic(replay)
                raise
            else:
                # A replay that returns normally must have consumed every recorded
                # body command, so the interaction sees state consistent with history.
                _check_body_consumed(replay)
            _raise_if_nondeterministic(replay)
            handler = handlers.query_handler(name) if kind == "query" else handlers.update_handler(name)
            if handler is None:
                raise ApplicationFailure.non_retryable_failure(f"{kind} {name} is not registered", missing_code, name)
            value = await _maybe_await(handler(*(payload.get("args") or [])))
            await self._complete_task(task, {
                "value": value,
                "message": f"{kind} completed",
                "started_at": started_at,
                "finished_at": _now(),
            })
        except Exception as exc:
            await self._fail_task(task, str(exc), exc, started_at=started_at)

    async def _execute_activity_task(self, task: dict[str, Any]) -> None:
        started_at = _now()
        payload = task.get("payload") or {}
        activity_type = payload.get("activityType") or task["type"].removeprefix("activity:")
        target = self.activities.get(activity_type)
        try:
            if target is None:
                raise ApplicationFailure.non_retryable_failure(f"activity {activity_type} is not registered", "ActivityNotRegistered", activity_type)
            await self._emit(task["id"], "started", "activity", f"started activity {activity_type}", {"activityType": activity_type})
            value = await self._run_activity(target, task, activity_type, payload.get("args") or [], timeout_seconds=task.get("lease_timeout_seconds") or None)
            await self._emit(task["id"], "completed", "activity", f"completed activity {activity_type}")
            await self._complete_task(task, {
                "value": value,
                "message": "activity completed",
                "started_at": started_at,
                "finished_at": _now(),
            })
        except Exception as exc:
            await self._emit(task["id"], "failed", "activity", str(exc))
            await self._fail_task(task, str(exc), exc, started_at=started_at)

    async def _run_workflow(self, target: Callable[..., Any] | type, task: dict[str, Any], payload: dict[str, Any], replay: WorkflowReplay, handlers: "WorkflowHandlers", *, query_mode: bool = False) -> Any:
        workflow.validate_workflow_sandbox(target)
        workflow_type = payload.get("workflowType") or task["type"].removeprefix("workflow:")
        if inspect.isclass(target):
            instance = target()
            run_method = workflow.workflow_run_method(target)
            workflow_fn = getattr(instance, run_method.__name__)
        else:
            workflow_fn = target

        runtime = workflow._WorkflowRuntime(
            workflow_id=payload.get("workflowId") or task["id"],
            workflow_run_id=payload.get("runId") or payload.get("workflowId") or task["id"],
            task_queue=task["queue"],
            workflow_type=workflow_type,
            execute_activity=lambda name, args, options: self._replay_activity_for_query(replay, name) if query_mode else self._execute_activity_command(task, replay, name, args, options),
            execute_child=lambda name, args, options: self._replay_child_for_query(replay, name) if query_mode else self._execute_child_command(task, replay, name, args, options),
            continue_as_new=lambda name, args, options: (_raise_query_ready("workflow continued as new") if query_mode else (_raise_continue_as_new(name, args, options))),
            sleep=lambda ms, scope: self._replay_timer_for_query(replay, ms) if query_mode else self._execute_timer_command(task, replay, ms, scope),
            condition=lambda predicate, timeout_ms, scope: self._replay_condition_for_query(predicate) if query_mode else self._execute_condition_command(task, replay, predicate, timeout_ms, scope),
            cancellation_requested=replay.is_cancellation_requested,
            set_handler=lambda kind, name, handler: handlers.set_handler(kind, name, handler),
            emit=lambda event: self._emit(task["id"], event.get("kind") or "progress", event.get("stage"), event.get("message"), event.get("details")) if not query_mode else _noop_emit(),
        )
        return await workflow.run_in_workflow_runtime(runtime, lambda: workflow_fn(*(payload.get("args") or [])))

    async def _execute_activity_command(self, workflow_task: dict[str, Any], replay: WorkflowReplay, name: str, args: list[Any], options: dict[str, Any]) -> Any:
        self._throw_if_cancelled(replay, options.get("cancellation_scope"))
        scheduled = _replay_command(lambda: replay.next_activity(name))
        if scheduled and scheduled.get("task_id"):
            task = await asyncio.to_thread(self.connection.get_task, scheduled["task_id"])
            if task["state"] == "succeeded":
                return (task.get("result") or {}).get("value")
            if task["state"] == "failed":
                if replay.is_activity_canceled(scheduled):
                    raise CancelledFailure(replay.activity_cancellation_reason(scheduled))
                if replay.has_activity_retry_scheduled(scheduled):
                    return await self._execute_activity_command(workflow_task, replay, name, args, options)
                raise ApplicationFailure(str(task.get("error") or "activity failed"), type="ActivityFailure")
            raise WorkflowBlocked(f"waiting for activity {name}")
        payload = workflow_task.get("payload") or {}
        await self._schedule_in_order(replay, self.connection.enqueue_task, {
            "type": f"activity:{name}",
            "namespace": workflow_task["namespace"],
            "queue": workflow_task["queue"],
            "payload": {
                "activityType": name,
                "workflowId": payload.get("workflowId") or workflow_task["id"],
                "workflowRunId": payload.get("runId"),
                "workflowTaskId": workflow_task["id"],
                "attempt": 1,
                "cancellationType": options.get("cancellation_type") or options.get("cancellationType"),
                "retry": options.get("retry"),
                "args": args,
            },
            "lease_timeout_seconds": _timeout_seconds(
                options.get("start_to_close_timeout")
                or options.get("schedule_to_close_timeout")
                or options.get("start_to_close_timeout_ms")
                or options.get("schedule_to_close_timeout_ms")
            ),
        })
        raise WorkflowBlocked(f"scheduled activity {name}")

    async def _execute_timer_command(self, workflow_task: dict[str, Any], replay: WorkflowReplay, duration_ms: int, cancellation_scope: str = "cancellable") -> None:
        self._throw_if_cancelled(replay, cancellation_scope)
        started = _replay_command(lambda: replay.next_timer(duration_ms))
        if started and started.get("task_id"):
            if replay.is_timer_fired(started):
                return
            raise WorkflowBlocked("waiting for timer")
        payload = workflow_task.get("payload") or {}
        await self._schedule_in_order(replay, self.connection.enqueue_task, {
            "type": "timer",
            "namespace": workflow_task["namespace"],
            "queue": workflow_task["queue"],
            "payload": {
                "workflowId": payload.get("workflowId") or workflow_task["id"],
                "workflowRunId": payload.get("runId"),
                "workflowTaskId": workflow_task["id"],
                "timerId": str(uuid.uuid4()),
                "durationMs": duration_ms,
                "fireAt": _iso_after_ms(duration_ms),
            },
        })
        raise WorkflowBlocked(f"scheduled timer for {duration_ms}ms")

    async def _execute_child_command(self, workflow_task: dict[str, Any], replay: WorkflowReplay, workflow_type: str, args: list[Any], options: dict[str, Any]) -> Any:
        self._throw_if_cancelled(replay, options.get("cancellation_scope"))
        started = _replay_command(lambda: replay.next_child(workflow_type))
        if started:
            child_workflow_id = _child_workflow_id_from_event(started)
            if not child_workflow_id:
                raise ApplicationFailure.non_retryable_failure("child workflow history is missing child workflow ID", "InvalidChildWorkflowHistory")
            child = await asyncio.to_thread(self.connection.get_workflow, _child_run_id_from_event(started) or child_workflow_id)
            if child["state"] == "succeeded":
                return (child.get("result") or {}).get("value")
            if child["state"] == "failed":
                raise ApplicationFailure(str(child.get("error") or "child workflow failed"), type="ChildWorkflowFailure")
            raise WorkflowBlocked(f"waiting for child workflow {workflow_type}")
        payload = workflow_task.get("payload") or {}
        child_workflow_id = options.get("workflow_id") or options.get("workflowId") or str(uuid.uuid4())
        await self._schedule_in_order(replay, self.connection.enqueue_task, {
            "type": f"workflow:{workflow_type}",
            "namespace": workflow_task["namespace"],
            "queue": options.get("task_queue") or options.get("taskQueue") or workflow_task["queue"],
            "payload": {
                "namespace": workflow_task["namespace"],
                "workflowType": workflow_type,
                "workflowId": child_workflow_id,
                "parentWorkflowId": payload.get("workflowId") or workflow_task["id"],
                "parentWorkflowRunId": payload.get("runId"),
                "parentWorkflowTaskId": workflow_task["id"],
                "parentCancellationType": options.get("cancellation_type") or options.get("cancellationType"),
                "runTimeoutMs": _duration_ms_nullable(options.get("workflow_run_timeout") or options.get("workflow_run_timeout_ms")),
                "retry": options.get("retry"),
                "args": args,
            },
            "lease_timeout_seconds": options.get("lease_timeout_seconds") or options.get("leaseTimeoutSeconds"),
        })
        raise WorkflowBlocked(f"scheduled child workflow {workflow_type}")

    async def _execute_condition_command(self, workflow_task: dict[str, Any], replay: WorkflowReplay, predicate: Callable[[], bool], timeout_ms: int | None, cancellation_scope: str) -> bool:
        self._throw_if_cancelled(replay, cancellation_scope)
        if predicate():
            return True
        if timeout_ms is None:
            raise WorkflowBlocked("waiting for condition")
        await self._execute_timer_command(workflow_task, replay, timeout_ms, cancellation_scope)
        return predicate()

    async def _replay_activity_for_query(self, replay: WorkflowReplay, name: str) -> Any:
        if replay.is_cancellation_requested():
            raise WorkflowQueryReady("workflow cancelled")
        scheduled = _replay_command(lambda: replay.next_activity(name))
        if not scheduled or not scheduled.get("task_id"):
            raise WorkflowQueryReady()
        task = await asyncio.to_thread(self.connection.get_task, scheduled["task_id"])
        if task["state"] == "succeeded":
            return (task.get("result") or {}).get("value")
        if task["state"] == "failed":
            if replay.is_activity_canceled(scheduled):
                raise WorkflowQueryReady("activity cancelled")
            if replay.has_activity_retry_scheduled(scheduled):
                return await self._replay_activity_for_query(replay, name)
            raise ApplicationFailure(str(task.get("error") or "activity failed"), type="ActivityFailure")
        raise WorkflowQueryReady(f"waiting for activity {name}")

    async def _replay_timer_for_query(self, replay: WorkflowReplay, duration_ms: int) -> None:
        if replay.is_cancellation_requested():
            raise WorkflowQueryReady("workflow cancelled")
        started = _replay_command(lambda: replay.next_timer(duration_ms))
        if not started or not started.get("task_id") or not replay.is_timer_fired(started):
            raise WorkflowQueryReady("waiting for timer")

    async def _replay_child_for_query(self, replay: WorkflowReplay, name: str) -> Any:
        if replay.is_cancellation_requested():
            raise WorkflowQueryReady("workflow cancelled")
        started = _replay_command(lambda: replay.next_child(name))
        if not started:
            raise WorkflowQueryReady()
        child_workflow_id = _child_workflow_id_from_event(started)
        if not child_workflow_id:
            raise ApplicationFailure.non_retryable_failure("child workflow history is missing child workflow ID", "InvalidChildWorkflowHistory")
        child = await asyncio.to_thread(self.connection.get_workflow, _child_run_id_from_event(started) or child_workflow_id)
        if child["state"] == "succeeded":
            return (child.get("result") or {}).get("value")
        if child["state"] == "failed":
            raise ApplicationFailure(str(child.get("error") or "child workflow failed"), type="ChildWorkflowFailure")
        raise WorkflowQueryReady(f"waiting for child workflow {name}")

    async def _replay_condition_for_query(self, predicate: Callable[[], bool]) -> bool:
        if predicate():
            return True
        raise WorkflowQueryReady("waiting for condition")

    async def _run_activity(self, target: Callable[..., Any], task: dict[str, Any], activity_type: str, args: list[Any], *, timeout_seconds: float | None = None) -> Any:
        async def heartbeat(details: dict[str, Any] | None) -> None:
            await asyncio.to_thread(self.connection.heartbeat_task, task["id"], self.identity, {
                "kind": "heartbeat",
                "stage": "activity",
                "message": f"activity {activity_type} heartbeat",
                "details": details,
            })

        async def emit(event: dict[str, Any]) -> None:
            await asyncio.to_thread(self.connection.append_task_event, task["id"], self.identity, event)

        runtime = activity._ActivityRuntime(task_id=task["id"], activity_type=activity_type, heartbeat=heartbeat, emit=emit)
        coro = activity.run_in_activity_runtime(runtime, lambda: target(*args))
        if timeout_seconds and timeout_seconds > 0:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        return await coro

    async def _complete_workflow_as_continued(self, task: dict[str, Any], command: workflow.ContinueAsNewCommand, started_at: str) -> None:
        payload = task.get("payload") or {}
        current_workflow_id = payload.get("workflowId") or task["id"]
        next_workflow_id = command.options.get("workflow_id") or command.options.get("workflowId") or f"{current_workflow_id}-continue-{uuid.uuid4()}"
        task_queue = command.options.get("task_queue") or command.options.get("taskQueue") or task["queue"]
        next_task = await asyncio.to_thread(self.connection.enqueue_task, {
            "type": f"workflow:{command.workflow_type}",
            "queue": task_queue,
            "namespace": task["namespace"],
            "payload": {
                "namespace": task["namespace"],
                "workflowType": command.workflow_type,
                "workflowId": next_workflow_id,
                "continuedFromWorkflowId": current_workflow_id,
                "runTimeoutMs": _duration_ms_nullable(command.options.get("workflow_run_timeout") or command.options.get("workflow_run_timeout_ms")),
                "retry": command.options.get("retry"),
                "args": list(command.args),
            },
            "lease_timeout_seconds": command.options.get("lease_timeout_seconds") or command.options.get("leaseTimeoutSeconds"),
        })
        await self._complete_task(task, {
            "message": "workflow continued as new",
            "continue_as_new": {
                "workflow_id": next_workflow_id,
                "workflow_type": command.workflow_type,
                "task_queue": task_queue,
                "task_id": next_task["id"],
            },
            "started_at": started_at,
            "finished_at": _now(),
        })

    async def _with_lease_renewal(self, task: dict[str, Any], fn: Callable[[], Awaitable[None]]) -> None:
        stopped = asyncio.Event()
        interval = heartbeat_interval(float(task.get("lease_timeout_seconds") or 30))

        async def renew_loop() -> None:
            while not stopped.is_set():
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=interval)
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    await asyncio.to_thread(self.connection.heartbeat_task, task["id"], self.identity, {
                        "kind": "heartbeat",
                        "stage": "lease",
                        "message": f"renewed {task['type']} lease",
                    })
                except Exception as exc:
                    if is_terminal_task_mutation(exc):
                        return

        renew_task = asyncio.create_task(renew_loop())
        try:
            await fn()
        finally:
            stopped.set()
            await renew_task

    async def _emit(self, task_id: str, kind: str, stage: str | None = None, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        try:
            await asyncio.to_thread(self.connection.append_task_event, task_id, self.identity, {"kind": kind, "stage": stage, "message": message, "details": details})
        except Exception:
            pass

    async def _complete_task(self, task: dict[str, Any], result: dict[str, Any]) -> None:
        try:
            await asyncio.to_thread(self.connection.complete_task, task["id"], self.identity, result)
        except Exception as exc:
            if not is_terminal_task_mutation(exc):
                raise

    async def _block_task(self, task: dict[str, Any], reason: str) -> None:
        try:
            await asyncio.to_thread(self.connection.block_task, task["id"], self.identity, reason)
        except Exception as exc:
            if not is_terminal_task_mutation(exc):
                raise

    async def _fail_task(self, task: dict[str, Any], message: str, exc: Exception, *, started_at: str | None = None) -> None:
        try:
            await asyncio.to_thread(self.connection.fail_task, task["id"], self.identity, message, {
                "message": message,
                "failure": failure_info(exc),
                "started_at": started_at or _now(),
                "finished_at": _now(),
            })
        except Exception as fail_exc:
            if not is_terminal_task_mutation(fail_exc):
                raise

    async def _schedule_in_order(self, replay: WorkflowReplay, enqueue: Callable[..., Any], *args: Any) -> Any:
        """Schedule a new command after every earlier one in this invocation.

        Commands issued concurrently (for example with ``asyncio.gather``) are
        then recorded in call order, which is the order replay consumes them.
        """
        state = self._command_locks.setdefault(replay, _CommandScheduler())
        state.pending += 1
        try:
            async with state.lock:
                # A failed earlier enqueue fails every later one, so history never
                # records a later command without the earlier one.
                if state.error is not None:
                    raise state.error
                try:
                    return await asyncio.to_thread(enqueue, *args)
                except Exception as exc:
                    state.error = exc
                    raise
        finally:
            state.pending -= 1

    async def _read_command_owners(self, history: list[dict[str, Any]]) -> dict[str, str]:
        """Read, once per replay, which task issued each command that could belong to an update.

        A command task's payload names its scheduling task and never changes.
        """
        owners: dict[str, str] = {}
        for task_id in ownership_candidates(history):
            command_task = await asyncio.to_thread(self.connection.get_task, task_id)
            command_payload = command_task.get("payload") or {}
            owner = command_payload.get("workflowTaskId") or command_payload.get("parentWorkflowTaskId")
            if owner:
                owners[task_id] = owner
        return owners

    async def _drain_commands(self, replay: WorkflowReplay) -> None:
        """Wait until every command this invocation started has settled.

        ``asyncio.gather`` reports the first exception, such as the first
        command's suspension, while later enqueues are still in flight. The
        task must not be blocked, completed or failed before they persist.
        """
        state = self._command_locks.get(replay)
        while state is not None and state.pending:
            # The lock is FIFO, so acquiring it waits for every queued enqueue.
            async with state.lock:
                pass

    def _throw_if_cancelled(self, replay: WorkflowReplay, cancellation_scope: str | None = "cancellable") -> None:
        if cancellation_scope == "non_cancellable" or not replay.is_cancellation_requested():
            return
        raise CancelledFailure(replay.cancellation_reason())

    def _start_task(self, task: dict[str, Any]) -> None:
        running = asyncio.create_task(self._execute(task))
        self._in_flight.add(running)
        running.add_done_callback(self._in_flight.discard)

    def _reap_finished_tasks(self) -> None:
        for running in tuple(self._in_flight):
            if not running.done():
                continue
            self._in_flight.discard(running)
            running.exception()

    async def _wait_for_task_slot(self) -> None:
        if not self._in_flight:
            return
        done, _ = await asyncio.wait(self._in_flight, return_when=asyncio.FIRST_COMPLETED)
        for running in done:
            self._in_flight.discard(running)
            running.exception()

    async def _drain_in_flight(self, timeout: float | None = None) -> None:
        if not self._in_flight:
            return
        pending = tuple(self._in_flight)
        self._in_flight.clear()
        drained = asyncio.gather(*pending, return_exceptions=True)
        if timeout is None or timeout < 0:
            await drained
            return
        try:
            await asyncio.wait_for(asyncio.shield(drained), timeout=timeout)
        except asyncio.TimeoutError:
            pass


class WorkflowBlocked(Exception):
    pass


class WorkflowQueryReady(Exception):
    pass


class _CommandScheduler:
    """Per-invocation state that schedules new commands one at a time, in call order."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.error: Exception | None = None
        self.pending = 0


class WorkflowHandlers:
    """Per-invocation handler registries.

    Replay supplies the recorded signal and update arguments; the runtime owns
    the handlers and invokes them.
    """

    def __init__(self, replay: WorkflowReplay):
        self.replay = replay
        self.query_handlers: dict[str, Callable[..., Any]] = {}
        self.update_handlers: dict[str, Callable[..., Any]] = {}

    def set_handler(self, kind: str, name: str, handler: Callable[..., Any]) -> None:
        if kind == "signal":
            for args in self.replay.signal_args(name):
                handler(*args)
            return
        if kind == "update":
            self.update_handlers[name] = handler
            for args in self.replay.completed_update_args(name):
                handler(*args)
            return
        self.query_handlers[name] = handler

    def query_handler(self, name: str) -> Callable[..., Any] | None:
        return self.query_handlers.get(name)

    def update_handler(self, name: str) -> Callable[..., Any] | None:
        return self.update_handlers.get(name)


def _raise_if_nondeterministic(replay: WorkflowReplay) -> None:
    if replay.determinism_error is not None:
        raise _determinism_violation(str(replay.determinism_error)) from None


def _check_body_consumed(replay: WorkflowReplay) -> None:
    """Run the completion check's leftover test; the first recorded determinism error wins."""
    try:
        replay.check_body_consumed()
    except DeterminismError:
        pass
    _raise_if_nondeterministic(replay)


def _replay_command(step: Callable[[], Any]) -> Any:
    """Run one replay step, translating a replay-owned determinism error into the public failure."""
    try:
        return step()
    except DeterminismError as exc:
        raise _determinism_violation(str(exc)) from None


def failure_info(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ApplicationFailure):
        return {
            "message": str(exc),
            "type": exc.type,
            "non_retryable": exc.non_retryable,
            "details": exc.details,
        }
    if isinstance(exc, CancelledFailure):
        return {"message": str(exc), "type": "CancelledFailure", "non_retryable": True}
    return {"message": str(exc), "type": exc.__class__.__name__}


def heartbeat_interval(lease_timeout_seconds: float) -> float:
    if lease_timeout_seconds <= 1:
        return 0.5
    return max(0.5, lease_timeout_seconds / 3)


def _connection_from_client(client: Client | Connection | None, connection: Connection | None) -> Connection:
    if connection is not None:
        return connection
    if isinstance(client, Client):
        return client.connection
    if isinstance(client, Connection):
        return client
    raise ValueError("Agent requires a Client or Connection")




def _workflow_registry(entries: dict[str, Callable[..., Any] | type] | Iterable[Callable[..., Any] | type]) -> dict[str, Callable[..., Any] | type]:
    if isinstance(entries, dict):
        return dict(entries)
    return {workflow.workflow_name(entry): entry for entry in entries}


def _activity_registry(entries: dict[str, Callable[..., Any]] | Iterable[Callable[..., Any]]) -> dict[str, Callable[..., Any]]:
    if isinstance(entries, dict):
        return dict(entries)
    return {activity.activity_name(entry): entry for entry in entries}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_after_ms(duration_ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + (duration_ms / 1000)))


def _timeout_seconds(value: Any) -> int | None:
    duration = _duration_ms_nullable(value)
    if duration is None:
        return None
    return max(1, round(duration / 1000))


def _duration_ms_nullable(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds() * 1000)
    return int(value)


def _child_workflow_id_from_event(event: dict[str, Any]) -> str | None:
    value = (event.get("attributes") or {}).get("child_workflow_id")
    return value if isinstance(value, str) else None


def _child_run_id_from_event(event: dict[str, Any]) -> str | None:
    value = (event.get("attributes") or {}).get("child_run_id")
    return value if isinstance(value, str) else None


def _determinism_violation(message: str) -> ApplicationFailure:
    return ApplicationFailure.non_retryable_failure(message, "WorkflowDeterminismViolation")


def _raise_continue_as_new(workflow_type: str, args: list[Any], options: dict[str, Any]) -> None:
    raise workflow.ContinueAsNewCommand(workflow_type, args, options)


def _raise_query_ready(message: str = "query handlers ready") -> None:
    raise WorkflowQueryReady(message)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _noop_emit() -> None:
    return None
