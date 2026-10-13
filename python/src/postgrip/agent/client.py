from __future__ import annotations

import asyncio
import enum
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from typing import Any, Literal, Unpack
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import OpenerDirector, Request, build_opener

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .._internal.config import validate_base_url
from .._internal.http import (
    CancellationAwareHTTPHandler,
    CancellationAwareHTTPSHandler,
    SafeRedirectHandler,
    read_bounded_response,
    run_cancellable,
)
from . import _signing
from .errors import TaskFailedError, TimeoutFailure
from .openapi import (
    OpenAPIClient,
    OperationId,
    openapi_auth_lane_for_request,
    resolve_openapi_operation,
)
from .types import (
    AgentSessionResponse,
    BackfillScheduleRequest,
    BackfillScheduleResponse,
    ClientExecuteWorkflowOptions,
    ClientStartWorkflowOptions,
    ConnectionOptions,
    CountWorkflowsOptions,
    CreateScheduleRequest,
    EnqueueTaskRequest,
    HealthResponse,
    IsolationTier,
    JsonValue,
    ListSchedulesOptions,
    ListTasksOptions,
    ListWorkflowsOptions,
    Namespace,
    PauseScheduleRequest,
    PollTaskResponse,
    ReadyResponse,
    RetryPolicy,
    Schedule,
    ScheduleCalendarSpec,
    ScheduleMissedRunPolicy,
    ScheduleOverlapPolicy,
    SignalWithStartWorkflowRequest,
    SignalWithStartWorkflowResponse,
    Task,
    TaskEvent,
    TaskEventInput,
    TaskEventPage,
    TaskResult,
    TriggerScheduleRequest,
    TriggerScheduleResponse,
    UnpauseScheduleRequest,
    UpdateScheduleRequest,
    WorkflowClientExecuteOptions,
    WorkflowClientStartOptions,
    WorkflowCountOptions,
    WorkflowExecution,
    WorkflowHistoryEvent,
    WorkflowHistoryPage,
    WorkflowIdReusePolicy,
    WorkflowListOptions,
    WorkflowUIMetadata,
)
from .workflow import workflow_name

class _Missing(enum.Enum):
    """Marks a required argument omitted from a signature that keeps it optional for position."""

    MISSING = enum.auto()


_MISSING = _Missing.MISSING
_POSTGRIP_UI_MEMO_KEY = "postgrip.ui"
DEFAULT_ADDRESS = "https://agentorchestrator1.postgrip.io"
_AGENT_MAX_RESPONSE_BYTES = 40 << 20
_HISTORY_PAGE_MAXIMUM_LIMIT = 500

# Same-origin redirects only; cancelling an async call closes its active socket.
_AGENT_OPENER: OpenerDirector = build_opener(
    SafeRedirectHandler(),
    CancellationAwareHTTPHandler(),
    CancellationAwareHTTPSHandler(),
)


def urlopen(request: Request, timeout: float | None = None) -> Any:
    """Open one Agent request through the composed Agent opener."""

    return _AGENT_OPENER.open(request, timeout=timeout)


def has_authorization_header(headers: dict[str, str]) -> bool:
    """Whether *headers* already carries an Authorization header, any casing.

    HTTP header names are case-insensitive and ``urllib.request.Request``
    normalizes them, so a caller passing ``{"authorization": "Bearer …"}`` — a
    perfectly valid spelling — did not match an exact-case ``"Authorization"``
    check. The configured token was then added under the capitalized name, both
    collapsed to one header, and the *added* one won: the explicit-header
    precedence this SDK documents was inverted, and a request could go out
    authenticated as the wrong tenant.
    """
    return any(name.lower() == "authorization" for name in headers)


def _iter_history_pages(
    fetch_page: Callable[[str | None], Mapping[str, Any]],
) -> Iterator[Any]:
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        page = fetch_page(cursor)
        items = page.get("items")
        if not isinstance(items, list):
            raise RuntimeError("postgrip-agent: history page is missing its items array")
        yield from items
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            return
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            raise RuntimeError("postgrip-agent: history page returned an empty next cursor")
        cursor = next_cursor.strip()
        if cursor in seen:
            raise RuntimeError("postgrip-agent: history page repeated its next cursor")
        seen.add(cursor)


class Connection:
    def __init__(
        self,
        address: str | None = None,
        *,
        timeout: float = 30,
        headers: dict[str, str] | None = None,
        auth_token: str | None = None,
        insecure_development: bool = False,
        agent_id: str | None = None,
        worker_id: str | None = None,
        agent_name: str | None = None,
        agent_host: str | None = None,
        agent_namespace: str = "default",
        agent_queue: str = "default",
        agent_access_token: str | None = None,
        agent_refresh_token: str | None = None,
        agent_access_expires_at: str | datetime | None = None,
        agent_signing_private_key: str | None = None,
    ):
        if not address:
            address = os.environ.get("POSTGRIP_AGENT_URL") or os.environ.get("POSTGRIP_URL") or DEFAULT_ADDRESS
        address = validate_base_url("Agent", address, insecure_development=insecure_development)
        self.address = address.rstrip("/")
        self.insecure_development = insecure_development
        self.timeout = timeout
        self.headers = dict(headers or {})
        # Management token, sent on every management-lane request. Required for
        # the sandbox APIs, which reject agent tokens. Its server-owned syntax
        # is intentionally opaque to the SDK.
        self.auth_token = (auth_token or os.environ.get("POSTGRIP_TOKEN") or "").strip() or None
        self._agent_id = agent_id or worker_id or os.environ.get("POSTGRIP_AGENT_ID")
        self._agent_name = agent_name
        self._agent_host = agent_host
        self._agent_namespace = os.environ.get("POSTGRIP_AGENT_NAMESPACE", agent_namespace) if agent_namespace == "default" else agent_namespace
        self._agent_queue = os.environ.get("POSTGRIP_AGENT_TASK_QUEUE", agent_queue) if agent_queue == "default" else agent_queue
        self._agent_access_token: str | None = agent_access_token or os.environ.get("POSTGRIP_AGENT_ACCESS_TOKEN")
        self._agent_refresh_token: str | None = agent_refresh_token or os.environ.get("POSTGRIP_AGENT_REFRESH_TOKEN")
        self._agent_access_expires_at = _parse_timestamp(agent_access_expires_at or os.environ.get("POSTGRIP_AGENT_ACCESS_EXPIRES_AT"))
        self._agent_lock = threading.RLock()
        self._agent_refresh_lock = threading.Lock()
        # Ed25519 keypair injected by the host agent for managed workflow
        # runtimes.
        signing_private_key = agent_signing_private_key or os.environ.get("POSTGRIP_AGENT_SIGNING_PRIVATE_KEY")
        self._agent_sign_priv: Ed25519PrivateKey | None = _signing.decode_private_key(signing_private_key) if signing_private_key else None
        self.openapi = OpenAPIClient(self._request_openapi)

    @classmethod
    async def connect(cls, address: str | None = None, **options: Unpack[ConnectionOptions]) -> "Connection":
        connection = cls(address, **options)
        await run_cancellable(connection.health)
        return connection

    def configure_agent_auth(
        self,
        *,
        agent_id: str | None = None,
        worker_id: str | None = None,
        agent_name: str | None = None,
        agent_host: str | None = None,
        namespace: str | None = None,
        queue: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        access_expires_at: str | datetime | None = None,
        signing_private_key: str | None = None,
    ) -> None:
        with self._agent_lock:
            resolved_agent_id = agent_id or worker_id
            if resolved_agent_id:
                self._agent_id = resolved_agent_id
            if agent_name:
                self._agent_name = agent_name
            if agent_host:
                self._agent_host = agent_host
            if namespace:
                self._agent_namespace = namespace
            if queue:
                self._agent_queue = queue
            if access_token:
                self._agent_access_token = access_token
            if refresh_token:
                self._agent_refresh_token = refresh_token
            if access_expires_at:
                self._agent_access_expires_at = _parse_timestamp(access_expires_at)
            if signing_private_key:
                self._agent_sign_priv = _signing.decode_private_key(signing_private_key)

    def request(self, method: str, path: str, body: Any = None, *, agent_auth: bool = False) -> Any:
        # Raw agent-authenticated requests preserve the legacy signing default.
        signing = "agent-task-v1" if agent_auth else ""
        return self._request(method, path, body, agent_auth=agent_auth, signing=signing)

    def _request_openapi(
        self,
        operation_id: OperationId,
        body: Any = None,
        *,
        path_parameters: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Resolve generated HTTP metadata, retaining the custom transport."""
        operation = resolve_openapi_operation(operation_id, path_parameters, query)
        agent_auth = operation.auth_lane == "agent" or (
            operation.auth_lane == "either" and self._has_agent_runtime_credentials()
        )
        return self._request(
            operation.method,
            operation.path,
            body,
            agent_auth=agent_auth,
            management_auth=operation.auth_lane != "public",
            signing=operation.signing,
            request_headers=headers,
        )

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        agent_auth: bool = False,
        management_auth: bool = True,
        signing: str = "",
        request_headers: dict[str, str] | None = None,
    ) -> Any:
        data = b"" if body is None else json.dumps(body).encode()
        auth_lane = openapi_auth_lane_for_request(method, path)
        # Preserve the raw request API's opt-in behavior for agent-only paths;
        # generated wrappers pass agent_auth explicitly. "Either" operations
        # retain their historical automatic lane selection.
        use_agent_auth = agent_auth or (
            auth_lane == "either" and self._has_agent_runtime_credentials()
        )
        if use_agent_auth:
            self.ensure_agent_session()
        headers = dict(self.headers)
        headers.update(request_headers or {})
        # Some CDN front-ends block urllib's default UA. Always send a stable
        # SDK identifier so behavior is consistent across local and proxied
        # deployments.
        headers.setdefault("User-Agent", "postgrip-agent-python")
        if use_agent_auth and self._agent_access_token:
            headers["Authorization"] = f"Bearer {self._agent_access_token}"
        elif not use_agent_auth and management_auth and self.auth_token and not has_authorization_header(headers):
            # An explicitly supplied header wins, so existing callers that
            # hand-build one keep working.
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        if use_agent_auth and signing == "agent-task-v1" and self._agent_sign_priv is not None:
            split = urlsplit(self.address + path)
            ts = int(time.time())
            headers[_signing.HEADER_AGENT_SIGNATURE_TIMESTAMP] = str(ts)
            headers[_signing.HEADER_AGENT_SIGNATURE_KEY_ID] = _signing.public_key_id(self._agent_sign_priv.public_key())
            headers[_signing.HEADER_AGENT_SIGNATURE] = _signing.sign_request(
                self._agent_sign_priv, method, split.path, split.query, ts, data,
            )
        # urllib treats `data=b""` as a GET-with-body, which is wrong; pass None for empty bodies.
        request = Request(self.address + path, data=(data or None) if body is not None else None, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = read_bounded_response(
                    response,
                    "Agent",
                    maximum_bytes=_AGENT_MAX_RESPONSE_BYTES,
                )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        except HTTPError as exc:
            try:
                raw = read_bounded_response(exc, "Agent", maximum_bytes=_AGENT_MAX_RESPONSE_BYTES)
            except ValueError as read_error:
                raise RuntimeError(str(read_error)) from exc
            finally:
                exc.close()
            if exc.code == 410 and urlsplit(path).path == "/api/v1/agent/poll":
                # Gone is terminal even if an intermediary strips or corrupts
                # the response body. Preserve valid directive fields while
                # making shutdown unconditionally reachable to the worker.
                try:
                    parsed = json.loads(raw.decode()) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}
                directive = parsed.get("directive")
                if not isinstance(directive, dict):
                    directive = {}
                parsed["directive"] = {**directive, "type": "shutdown"}
                return parsed
            raise RuntimeError(raw.decode() or str(exc)) from exc
        return json.loads(raw.decode()) if raw else None

    def ensure_agent_session(self, *, namespace: str | None = None, queue: str | None = None, agent_id: str | None = None, worker_id: str | None = None) -> bool:
        with self._agent_lock:
            if namespace:
                self._agent_namespace = namespace
            if queue:
                self._agent_queue = queue
            resolved_agent_id = agent_id or worker_id
            if resolved_agent_id:
                self._agent_id = resolved_agent_id
            if self._agent_access_token and self._agent_access_expires_at > time.time() + 30:
                return True

        with self._agent_refresh_lock:
            with self._agent_lock:
                if self._agent_access_token and self._agent_access_expires_at > time.time() + 30:
                    return True
                refresh_token = self._agent_refresh_token

            if refresh_token:
                self._apply_agent_session(
                    self.openapi.refresh_agent_session({"refreshToken": refresh_token})
                )
                return True

            raise RuntimeError("postgrip-agent: managed runtime credentials are required; submit workflow.runtime work to a host agent instead of enrolling SDK agents")

    def _has_agent_runtime_credentials(self) -> bool:
        with self._agent_lock:
            return bool(self._agent_access_token or self._agent_refresh_token)

    def _apply_agent_session(self, session: AgentSessionResponse) -> None:
        with self._agent_lock:
            self._agent_id = session.get("agentId") or self._agent_id
            self._agent_access_token = session.get("accessToken")
            self._agent_refresh_token = session.get("refreshToken")
            self._agent_access_expires_at = _parse_timestamp(session.get("accessExpiresAt"))

    def health(self) -> HealthResponse:
        return self.openapi.health()

    def ready(self) -> ReadyResponse:
        return self.openapi.ready()

    def list_namespaces(self) -> list[Namespace]:
        return self.openapi.list_namespaces()

    def create_namespace(self, name: str) -> Namespace:
        return self.openapi.create_namespace({"name": name})

    def enqueue_task(self, request: EnqueueTaskRequest) -> Task:
        if _runtime_only_task_type(str(request.get("type") or "")) and not self._has_agent_runtime_credentials():
            raise RuntimeError("postgrip-agent: workflow tasks can only be enqueued from a managed runtime; submit workflow.runtime to an agent pool")
        return self.openapi.enqueue_task(request)

    def list_tasks(self, **options: Unpack[ListTasksOptions]) -> list[Task]:
        return self.openapi.list_tasks(**_query_options(options))

    def get_task(self, task_id: str) -> Task:
        return self.openapi.get_task(task_id)

    def get_task_events_page(
        self,
        task_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> TaskEventPage:
        return self.openapi.list_task_events(task_id, cursor=cursor, limit=limit)

    def iter_task_events(self, task_id: str) -> Iterator[TaskEvent]:
        return _iter_history_pages(
            lambda cursor: self.get_task_events_page(
                task_id,
                cursor=cursor,
                limit=_HISTORY_PAGE_MAXIMUM_LIMIT,
            )
        )

    def get_task_events(self, task_id: str) -> list[TaskEvent]:
        return list(self.iter_task_events(task_id))

    def complete_task(self, task_id: str, agent_id: str | None = None, result: TaskResult | Literal[_Missing.MISSING] = _MISSING, *, worker_id: str | None = None) -> Task:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        if result is _MISSING:
            raise TypeError("result is required")
        self.ensure_agent_session(agent_id=resolved_agent_id)
        return self.openapi.complete_agent_task(task_id, {"result": result}, agent_id=resolved_agent_id)

    def block_task(self, task_id: str, agent_id: str | None = None, reason: str | None = None, *, worker_id: str | None = None) -> Task:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        self.ensure_agent_session(agent_id=resolved_agent_id)
        return self.openapi.block_agent_task(task_id, {"reason": reason}, agent_id=resolved_agent_id)

    def fail_task(self, task_id: str, agent_id: str | None = None, error: str | Literal[_Missing.MISSING] = _MISSING, result: TaskResult | None = None, *, worker_id: str | None = None) -> Task:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        if error is _MISSING:
            raise TypeError("error is required")
        self.ensure_agent_session(agent_id=resolved_agent_id)
        return self.openapi.fail_agent_task(task_id, {"error": error, "result": result}, agent_id=resolved_agent_id)

    def heartbeat_task(self, task_id: str, agent_id: str | None = None, event: TaskEventInput | None = None, *, worker_id: str | None = None) -> Task:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        self.ensure_agent_session(agent_id=resolved_agent_id)
        return self.openapi.heartbeat_agent_task(task_id, {"event": event}, agent_id=resolved_agent_id)

    def append_task_event(self, task_id: str, agent_id: str | None = None, event: TaskEventInput | Literal[_Missing.MISSING] = _MISSING, *, worker_id: str | None = None) -> TaskEvent:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        if event is _MISSING:
            raise TypeError("event is required")
        self.ensure_agent_session(agent_id=resolved_agent_id)
        return self.openapi.append_agent_task_event(task_id, {"event": event}, agent_id=resolved_agent_id)

    def poll_task_response(self, *, namespace: str, queue: str, agent_id: str | None = None, worker_id: str | None = None, wait_seconds: int = 20, task_types: list[str] | tuple[str, ...] | None = None) -> PollTaskResponse:
        resolved_agent_id = _resolve_agent_id(agent_id, worker_id)
        self.ensure_agent_session(namespace=namespace, queue=queue, agent_id=resolved_agent_id)
        return self.openapi.poll_agent_task(
            namespace=namespace,
            queue=queue,
            agent_id=resolved_agent_id,
            wait_seconds=wait_seconds,
            task_types=",".join(task_types) if task_types else None,
        ) or {}

    def poll_task(self, *, namespace: str, queue: str, agent_id: str | None = None, worker_id: str | None = None, wait_seconds: int = 20, task_types: list[str] | tuple[str, ...] | None = None) -> Task | None:
        response = self.poll_task_response(
            namespace=namespace,
            queue=queue,
            agent_id=agent_id,
            worker_id=worker_id,
            wait_seconds=wait_seconds,
            task_types=task_types,
        )
        return response.get("task")

    def get_workflow(self, workflow_id_or_run_id: str) -> WorkflowExecution:
        return self.openapi.get_workflow(workflow_id_or_run_id)

    def get_workflow_history_page(
        self,
        workflow_id_or_run_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> WorkflowHistoryPage:
        return self.openapi.list_workflow_history(
            workflow_id_or_run_id,
            cursor=cursor,
            limit=limit,
        )

    def iter_workflow_history(self, workflow_id_or_run_id: str) -> Iterator[WorkflowHistoryEvent]:
        return _iter_history_pages(
            lambda cursor: self.get_workflow_history_page(
                workflow_id_or_run_id,
                cursor=cursor,
                limit=_HISTORY_PAGE_MAXIMUM_LIMIT,
            )
        )

    def get_workflow_history(self, workflow_id_or_run_id: str) -> list[WorkflowHistoryEvent]:
        return list(self.iter_workflow_history(workflow_id_or_run_id))

    def list_workflows(self, **options: Unpack[ListWorkflowsOptions]) -> list[WorkflowExecution]:
        query_options, search = _generated_workflow_query(options)
        return self.openapi.list_workflows(search=search, **query_options)

    def count_workflows(self, **options: Unpack[CountWorkflowsOptions]) -> int:
        query_options, search = _generated_workflow_query(options)
        return int(self.openapi.count_workflows(search=search, **query_options)["count"])

    def signal_workflow(self, workflow_id_or_run_id: str, name: str, args: list[Any] | None = None) -> WorkflowHistoryEvent:
        return self.openapi.signal_workflow(workflow_id_or_run_id, {"name": name, "args": args or []})

    def signal_with_start_workflow(self, workflow_id: str, request: SignalWithStartWorkflowRequest) -> SignalWithStartWorkflowResponse:
        if not self._has_agent_runtime_credentials():
            raise RuntimeError("postgrip-agent: signal-with-start can only run from a managed runtime; submit workflow.runtime to an agent pool")
        return self.openapi.signal_with_start_workflow(workflow_id, request)

    def cancel_workflow(self, workflow_id_or_run_id: str, reason: str | None = None) -> WorkflowHistoryEvent:
        return self.openapi.cancel_workflow(workflow_id_or_run_id, {"reason": reason or ""})

    def terminate_workflow(self, workflow_id_or_run_id: str, reason: str | None = None) -> WorkflowHistoryEvent:
        return self.openapi.terminate_workflow(workflow_id_or_run_id, {"reason": reason or ""})

    def create_schedule(self, request: CreateScheduleRequest) -> Schedule:
        return self.openapi.create_schedule(request)

    def list_schedules(self, **options: Unpack[ListSchedulesOptions]) -> list[Schedule]:
        return self.openapi.list_schedules(**_query_options(options))

    def get_schedule(self, schedule_id: str) -> Schedule:
        return self.openapi.get_schedule(schedule_id)

    def update_schedule(self, schedule_id: str, request: UpdateScheduleRequest) -> Schedule:
        return self.openapi.update_schedule(schedule_id, request)

    def delete_schedule(self, schedule_id: str) -> Schedule:
        return self.openapi.delete_schedule(schedule_id)

    def pause_schedule(self, schedule_id: str, request: PauseScheduleRequest | None = None) -> Schedule:
        return self.openapi.pause_schedule(schedule_id, request or {})

    def unpause_schedule(self, schedule_id: str, request: UnpauseScheduleRequest | None = None) -> Schedule:
        return self.openapi.unpause_schedule(schedule_id, request or {})

    def trigger_schedule(self, schedule_id: str, request: TriggerScheduleRequest | None = None) -> TriggerScheduleResponse:
        return self.openapi.trigger_schedule(schedule_id, request or {})

    def backfill_schedule(self, schedule_id: str, request: BackfillScheduleRequest) -> BackfillScheduleResponse:
        return self.openapi.backfill_schedule(schedule_id, request)


class Client:
    def __init__(self, connection: Connection | None = None):
        self.connection = connection or Connection()
        self.workflow = WorkflowClient(self.connection)
        self.task = TaskClient(self.connection)
        self.schedule = ScheduleClient(self.connection)
        # Imported here rather than at module scope: sandbox.py imports
        # Connection for typing only, and a top-level import would cycle.
        from .sandbox import SandboxClient

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


def _runtime_only_task_type(task_type: str) -> bool:
    task_type = task_type.strip()
    return (
        task_type == "timer"
        or task_type.startswith("workflow:")
        or task_type.startswith("activity:")
        or task_type.startswith("query:")
        or task_type.startswith("update:")
    )


def _query_options(options: Mapping[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for key, value in options.items():
        if value is None:
            continue
        if key == "search_attributes":
            for search_key, search_value in value.items():
                query[f"search.{search_key}"] = search_value
            continue
        query[key] = value
    return query


def _generated_workflow_query(options: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    query = {
        key: value
        for key, value in options.items()
        if key != "search_attributes" and value is not None
    }
    search_attributes = options.get("search_attributes")
    search = dict(search_attributes.items()) if search_attributes else {}
    return query, search or None


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


def _resolve_agent_id(agent_id: str | None, worker_id: str | None) -> str:
    resolved = agent_id or worker_id
    if not resolved:
        raise TypeError("agent_id is required")
    return resolved


def _definition_name(value: Any) -> str:
    return value if isinstance(value, str) else value.name


def _duration_ms(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds() * 1000)
    return int(value)


def _parse_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
