"""Agent HTTP, signing and delegated-session adapter."""

from __future__ import annotations

from dataclasses import dataclass
import enum
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from collections.abc import Iterator, Mapping
from typing import Any, Literal, Unpack
from urllib.parse import parse_qs, urlsplit
from urllib.request import OpenerDirector, Request, build_opener

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .._internal.config import validate_base_url
from .._internal.http import (
    CancellationAwareHTTPHandler,
    CancellationAwareHTTPSHandler,
    ResponseTooLarge,
    SafeRedirectHandler,
    run_cancellable,
)
from .._internal.transport import Executor, RetryConfig
from . import _history, _signing
from .errors import AgentAPIError
from .openapi import (
    _OPERATION_TABLE,
    OpenAPIClient,
    OperationId,
    resolve_openapi_operation,
)
from .types import (
    AgentSessionResponse,
    BackfillScheduleRequest,
    BackfillScheduleResponse,
    CancelTaskRequest,
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


# Same-origin redirects only; cancelling an async call closes its active socket.
_AGENT_OPENER: OpenerDirector = build_opener(
    SafeRedirectHandler(),
    CancellationAwareHTTPHandler(),
    CancellationAwareHTTPSHandler(),
)


def urlopen(request: Request, timeout: float | None = None) -> Any:
    """Open one Agent request through the composed Agent opener."""

    return _AGENT_OPENER.open(request, timeout=timeout)


class _ModuleOpener:
    """Opens through this module's ``urlopen`` at call time, so it can be replaced."""

    def open(self, request: Request, timeout: float | None = None) -> Any:
        return urlopen(request, timeout=timeout)


# The contract default wait_seconds the server holds a poll for when it is omitted.
_DEFAULT_POLL_WAIT_SECONDS = 20


@dataclass(frozen=True)
class _RawOperation:
    """The annotations a raw ``Connection.request`` call runs under."""

    operation_id: str
    method: str
    path: str
    auth_lane: str
    safety: str
    retry: str
    signing: str
    streaming_request: bool = False
    websocket: bool = False
    idempotency: str = "none"
    header_parameters: tuple[str, ...] = ()


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
        enable_retries: bool = False,
    ):
        address = validate_base_url("Agent", _resolve_address(address), insecure_development=insecure_development)
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
        self._executor = Executor(
            plane="Agent",
            base_url=self.address,
            opener=_ModuleOpener(),
            management_token=self.auth_token,
            retry=RetryConfig(enabled=enable_retries, max_attempts=3, max_delay=2.0, retry_after_max=30.0),
            timeout=timeout,
            create_error=AgentAPIError._from_fields,
            max_response_bytes=_AGENT_MAX_RESPONSE_BYTES,
            delegated_credentials=self,
            sign=self._sign_agent_request,
        )
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
        """Send a raw request under the annotations of the generated operation it
        matches. ``agent_auth`` uses the delegated session and the legacy
        agent-task-v1 signing default; an unmatched path is a management request."""
        method = method.upper()
        matched = _match_operation(method, path)
        lane = "agent" if agent_auth else (matched.auth_lane if matched is not None else "management")
        operation = _RawOperation(
            operation_id=matched.operation_id.value if matched is not None else "rawRequest",
            method=method,
            path=path,
            auth_lane=lane,
            safety=matched.safety if matched is not None else "mutation",
            retry=matched.retry if matched is not None else "none",
            signing="agent-task-v1" if agent_auth else "",
        )
        return self._execute(operation, body)

    def _request_openapi(
        self,
        operation_id: OperationId,
        body: Any = None,
        *,
        path_parameters: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Run one generated operation through the shared executor."""
        return self._execute(resolve_openapi_operation(operation_id, path_parameters, query), body, headers)

    def _execute(self, operation: Any, body: Any, headers: dict[str, str] | None = None) -> Any:
        poll = urlsplit(operation.path).path == "/api/v1/agent/poll"
        call_headers = dict(headers or {})
        # The executor checks a caller's Idempotency-Key, sends it only where the
        # operation declares it, and lets a keyed mutation retry.
        idempotency_key = call_headers.pop("Idempotency-Key", None)
        try:
            response = self._executor.exchange(
                operation,
                body=body,
                idempotency_key=idempotency_key,
                # The connection's headers and timeout are read on every call, so
                # later changes apply here as they do in the upload and relay adapters.
                headers={**self.headers, **call_headers},
                # Poll Gone is a terminal shutdown directive, and a long poll's
                # server hold counts against its lifetime, so it gets headroom.
                accepted_statuses=frozenset({410}) if poll else frozenset(),
                timeout=max(self.timeout, _poll_wait_seconds(operation.path) + 30) if poll else self.timeout,
            )
        except ResponseTooLarge as exc:
            raise RuntimeError(str(exc)) from None
        raw = response.body
        if response.status == 410:
            # Gone is terminal even if an intermediary strips or corrupts the
            # response body. Preserve valid directive fields while making
            # shutdown unconditionally reachable to the worker.
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
        if not raw:
            return None
        try:
            return json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            # The body is server content, so the error names only the request.
            raise RuntimeError(
                f"postgrip-agent: {operation.method} {operation.path} -> {response.status} (parse failed)"
            ) from None

    def has_delegated(self) -> bool:
        """The executor's credential check for the either lane."""
        return self._has_agent_runtime_credentials()

    def delegated(self) -> str:
        """The executor's credential hook: refreshes the session when needed before every attempt."""
        self.ensure_agent_session()
        with self._agent_lock:
            return self._agent_access_token or ""

    def _sign_agent_request(self, method: str, url: str, headers: dict[str, str], body: bytes) -> None:
        """Apply the agent-task-v1 signature over the exact encoded body. Without
        an injected signing key the request is sent unsigned, as before."""
        priv = self._agent_sign_priv
        if priv is None:
            return
        split = urlsplit(url)
        ts = int(time.time())
        headers[_signing.HEADER_AGENT_SIGNATURE_TIMESTAMP] = str(ts)
        headers[_signing.HEADER_AGENT_SIGNATURE_KEY_ID] = _signing.public_key_id(priv.public_key())
        headers[_signing.HEADER_AGENT_SIGNATURE] = _signing.sign_request(priv, method, split.path, split.query, ts, body)

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

    def enqueue_task(self, request: EnqueueTaskRequest, *, idempotency_key: str | None = None) -> Task:
        """Send a task.

        An ``idempotency_key`` (1 to 128 visible ASCII characters) makes the
        send safe to repeat for 24 hours: a resend with the same key and request
        answers the first task instead of enqueueing another, and a connection
        with ``enable_retries`` retries it. Reusing the key with another request
        answers 409 ``IDEMPOTENCY_CONFLICT``. Without a key every send runs.
        """
        if _runtime_only_task_type(str(request.get("type") or "")) and not self._has_agent_runtime_credentials():
            raise RuntimeError("postgrip-agent: workflow tasks can only be enqueued from a managed runtime; submit workflow.runtime to an agent pool")
        return self.openapi.enqueue_task(request, idempotency_key=idempotency_key or None)

    def cancel_task(self, task_id: str, reason: str | None = None) -> Task:
        """End a task that has not finished.

        The task becomes ``failed``, with ``result.failure.type``
        ``TaskCancelled`` and the reason, when given, in its ``error``. A queued
        task is never leased; a leased task's Agent stops it on its next
        heartbeat. Cancelling a task already cancelled answers it unchanged, so
        a resend is safe. A task that already finished raises 409
        ``TASK_TERMINAL``, and a workflow's own task 409
        ``TASK_OWNED_BY_WORKFLOW``: cancel its workflow instead.
        """
        request: CancelTaskRequest = {} if reason is None else {"reason": reason}
        return self.openapi.cancel_task(task_id, request)

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
        return _history.iter_task_events(self, task_id)

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
        return _history.iter_workflow_history(self, workflow_id_or_run_id)

    def get_workflow_history(self, workflow_id_or_run_id: str) -> list[WorkflowHistoryEvent]:
        return list(self.iter_workflow_history(workflow_id_or_run_id))

    def list_workflows(self, **options: Unpack[ListWorkflowsOptions]) -> list[WorkflowExecution]:
        query_options, search = _generated_workflow_query(options)
        return self.openapi.list_workflows(search=search, **query_options)

    def count_workflows(self, **options: Unpack[CountWorkflowsOptions]) -> int:
        query_options, search = _generated_workflow_query(options)
        return int(self.openapi.count_workflows(search=search, **query_options)["count"])

    def signal_workflow(self, workflow_id_or_run_id: str, name: str, args: list[Any] | None = None, *, idempotency_key: str | None = None) -> WorkflowHistoryEvent:
        """Signal a running workflow; ``idempotency_key`` is as for :meth:`enqueue_task`."""
        return self.openapi.signal_workflow(
            workflow_id_or_run_id, {"name": name, "args": args or []}, idempotency_key=idempotency_key or None,
        )

    def signal_with_start_workflow(self, workflow_id: str, request: SignalWithStartWorkflowRequest, *, idempotency_key: str | None = None) -> SignalWithStartWorkflowResponse:
        """Signal a workflow, starting it first when none runs; ``idempotency_key``
        is as for :meth:`enqueue_task`, and a keyed resend never starts another run."""
        if not self._has_agent_runtime_credentials():
            raise RuntimeError("postgrip-agent: signal-with-start can only run from a managed runtime; submit workflow.runtime to an agent pool")
        return self.openapi.signal_with_start_workflow(workflow_id, request, idempotency_key=idempotency_key or None)

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


def _resolve_address(explicit: str | None) -> str:
    """Return the first configured Agent Orchestrator address.

    The explicit argument wins, then the orchestrator URL a host agent injects
    into a managed workflow runtime, then ``POSTGRIP_AGENT_URL``,
    ``POSTGRIP_URL`` and the built-in cloud address.
    """
    managed_runtime_address = (
        os.environ.get("POSTGRIP_AGENTORCHESTRATOR_URL")
        if os.environ.get("POSTGRIP_AGENT_MANAGED_RUNTIME") == "true"
        else None
    )
    return (
        explicit
        or managed_runtime_address
        or os.environ.get("POSTGRIP_AGENT_URL")
        or os.environ.get("POSTGRIP_URL")
        or DEFAULT_ADDRESS
    )


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


def _match_operation(method: str, path: str) -> Any:
    """The resolved generated operation a raw method and path match, if any."""
    request_path = path.partition("?")[0]
    for operation_id, operation in _OPERATION_TABLE.items():
        if operation.method != method:
            continue
        pattern = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", operation.path)
        found = re.fullmatch(pattern, request_path)
        if found is not None:
            return resolve_openapi_operation(operation_id, found.groupdict())
    return None


def _poll_wait_seconds(path: str) -> int:
    """The poll's wait_seconds, or the contract default when it is omitted or invalid."""
    values = parse_qs(urlsplit(path).query).get("wait_seconds")
    try:
        wait = int(values[0]) if values else _DEFAULT_POLL_WAIT_SECONDS
    except ValueError:
        return _DEFAULT_POLL_WAIT_SECONDS
    return wait if wait >= 0 else _DEFAULT_POLL_WAIT_SECONDS
