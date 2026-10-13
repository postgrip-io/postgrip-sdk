"""Agent HTTP, signing and delegated-session adapter."""

from __future__ import annotations

import enum
import json
import os
import threading
import time
from datetime import datetime, timezone
from collections.abc import Callable, Iterator, Mapping
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
    has_authorization_header,
    read_bounded_response,
    run_cancellable,
)
from . import _signing
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
    ConnectionOptions,
    CountWorkflowsOptions,
    CreateScheduleRequest,
    EnqueueTaskRequest,
    HealthResponse,
    ListSchedulesOptions,
    ListTasksOptions,
    ListWorkflowsOptions,
    Namespace,
    PauseScheduleRequest,
    PollTaskResponse,
    ReadyResponse,
    Schedule,
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
    WorkflowExecution,
    WorkflowHistoryEvent,
    WorkflowHistoryPage,
)

class _Missing(enum.Enum):
    """Marks a required argument omitted from a signature that keeps it optional for position."""

    MISSING = enum.auto()


_MISSING = _Missing.MISSING


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


def _resolve_agent_id(agent_id: str | None, worker_id: str | None) -> str:
    resolved = agent_id or worker_id
    if not resolved:
        raise TypeError("agent_id is required")
    return resolved


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
