from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPConnection, HTTPSConnection
import json
import os
import random
import re
import socket
from threading import Event, Thread
import time
from typing import Any, Literal, TypeVar, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, OpenerDirector, Request, build_opener

from .._internal.config import validate_base_url, validate_management_token

from .openapi import (
    CheckWorkerResponseBody,
    GetWorkerJobResponseBody,
    GetWorkerResponseBody,
    WorkerOrchestratorHealthResponseBody,
    ListWorkerAssignmentsResponseBody,
    ListWorkerJobsResponseBody,
    ListWorkerOperationalLogsResponseBody,
    ListWorkerSecurityLogsResponseBody,
    ListWorkersResponseBody,
    OpenAPIClient,
    OperationId,
    PlaceWorkerInMaintenanceResponseBody,
    ResumeWorkerFromMaintenanceResponseBody,
    UpgradeWorkerResponseBody,
    resolve_openapi_operation,
)

T = TypeVar("T")
_RETRYABLE_STATUS = {408, 429, 502, 503, 504}
_MAX_RESPONSE_BYTES = 4 << 20
_REQUEST_CANCEL_EVENT: ContextVar[Event | None] = ContextVar("postgrip_worker_request_cancel", default=None)


class _RequestCancelled(Exception):
    pass


class _CancellationAwareConnection:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cancel_event = _REQUEST_CANCEL_EVENT.get()
        self._request_done = Event()
        self._receiving_response = False
        self._response_open = False
        self._active_socket: socket.socket | None = None
        if self._cancel_event is not None:
            Thread(target=self._watch_for_cancellation, daemon=True).start()

    def _watch_for_cancellation(self) -> None:
        assert self._cancel_event is not None
        while not self._request_done.wait(0.01):
            if self._cancel_event.is_set():
                active_socket = self._active_socket
                if active_socket is not None:
                    try:
                        active_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                super().close()
                return

    def connect(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise OSError("request cancelled")
        super().connect()
        self._active_socket = self.sock
        if self._cancel_event is not None and self._cancel_event.is_set():
            try:
                if self._active_socket is not None:
                    self._active_socket.shutdown(socket.SHUT_RDWR)
            finally:
                super().close()
            raise OSError("request cancelled")

    def getresponse(self) -> Any:
        self._receiving_response = True
        try:
            response = super().getresponse()
        except BaseException:
            self._request_done.set()
            raise
        finally:
            self._receiving_response = False
        self._response_open = True
        close_response = response.close

        def close() -> None:
            try:
                close_response()
            finally:
                self._response_open = False
                self._request_done.set()

        response.close = close
        return response

    def close(self) -> None:
        super().close()
        if not self._receiving_response and not self._response_open:
            self._request_done.set()


class _CancellationAwareHTTPConnection(_CancellationAwareConnection, HTTPConnection):
    pass


class _CancellationAwareHTTPSConnection(_CancellationAwareConnection, HTTPSConnection):
    pass


class _CancellationAwareHTTPHandler(HTTPHandler):
    handler_order = 400

    def http_open(self, request: Request) -> Any:
        return self.do_open(_CancellationAwareHTTPConnection, request)


class _CancellationAwareHTTPSHandler(HTTPSHandler):
    handler_order = 400

    def https_open(self, request: Request) -> Any:
        return self.do_open(
            _CancellationAwareHTTPSConnection,
            request,
            context=getattr(self, "_context", None),
            check_hostname=getattr(self, "_check_hostname", None),
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _redirect_safe_opener(opener: OpenerDirector | None) -> OpenerDirector:
    https_context = None
    https_check_hostname = None
    if opener is not None:
        for handler in opener.handlers:
            if isinstance(handler, HTTPSHandler):
                https_context = getattr(handler, "_context", None)
                https_check_hostname = getattr(handler, "_check_hostname", None)
                break
    cancellation_handlers = (
        _CancellationAwareHTTPHandler(),
        _CancellationAwareHTTPSHandler(context=https_context, check_hostname=https_check_hostname),
    )
    if opener is None:
        return build_opener(_NoRedirect(), *cancellation_handlers)
    redirect_methods = ("http_error_301", "http_error_302", "http_error_303", "http_error_307", "http_error_308")
    handlers = [handler for handler in opener.handlers if not any(hasattr(handler, name) for name in redirect_methods)]
    if len(handlers) == len(opener.handlers):
        opener.add_handler(_NoRedirect())
        for handler in cancellation_handlers:
            opener.add_handler(handler)
        return opener
    return build_opener(*handlers, _NoRedirect(), *cancellation_handlers)


@dataclass(frozen=True)
class WorkerAPIError(Exception):
    status: int
    code: str
    message: str
    request_id: str = ""
    details: Mapping[str, Any] | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        return f"postgrip-worker: {self.code} (HTTP {self.status}): {self.message}"


class WorkerClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        insecure_development: bool = False,
        enable_retries: bool = False,
        follow_interval: float = 2.0,
        timeout: float = 30.0,
        opener: OpenerDirector | None = None,
    ) -> None:
        base_url = validate_base_url("Worker", base_url, insecure_development=insecure_development)
        token = validate_management_token(token)
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token
        self._enable_retries = enable_retries
        self._follow_interval = max(follow_interval, 0.001)
        self._timeout = timeout
        self._opener = _redirect_safe_opener(opener)
        self.openapi = OpenAPIClient(self._openapi_transport)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> WorkerClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_WORKER_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    def health(self) -> WorkerOrchestratorHealthResponseBody:
        return cast(WorkerOrchestratorHealthResponseBody, self._request(OperationId.WORKER_ORCHESTRATOR_HEALTH))

    def _openapi_transport(
        self,
        operation_id: OperationId,
        body: Any = None,
        *,
        path_parameters: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = headers or {}
        idempotency_key = request_headers.get("Idempotency-Key")
        if idempotency_key is not None and re.fullmatch(r"[!-~]{1,128}", idempotency_key) is None:
            raise ValueError("idempotency_key must contain 1 to 128 visible ASCII characters")
        return self._request(
            operation_id,
            path=path_parameters,
            query=query,
            idempotency_key=idempotency_key,
        )

    def list(self, *, page_size: int | None = None, page_token: str | None = None,
             status: str | None = None, trust_state: str | None = None) -> ListWorkersResponseBody:
        return cast(ListWorkersResponseBody, self._request(OperationId.LIST_WORKERS, query={
            "pageSize": page_size, "pageToken": page_token, "status": status, "trustState": trust_state,
        }))

    def pages(self, **options: Any) -> Iterator[ListWorkersResponseBody]:
        page_token = options.pop("page_token", None)
        while True:
            page = self.list(page_token=page_token, **options)
            yield page
            page_token = page.get("nextPageToken")
            if not page_token:
                return

    def get(self, worker_id: str) -> GetWorkerResponseBody:
        return cast(GetWorkerResponseBody, self._request(OperationId.GET_WORKER, path={"workerId": worker_id}))

    def assignments(self, worker_id: str) -> ListWorkerAssignmentsResponseBody:
        return cast(ListWorkerAssignmentsResponseBody, self._request(OperationId.LIST_WORKER_ASSIGNMENTS, path={"workerId": worker_id}))

    def jobs(self, worker_id: str, *, page_size: int | None = None, page_token: str | None = None,
             state: str | None = None) -> ListWorkerJobsResponseBody:
        return cast(ListWorkerJobsResponseBody, self._request(OperationId.LIST_WORKER_JOBS,
            path={"workerId": worker_id}, query={"pageSize": page_size, "pageToken": page_token, "state": state}))

    def job_pages(self, worker_id: str, **options: Any) -> Iterator[ListWorkerJobsResponseBody]:
        page_token = options.pop("page_token", None)
        while True:
            page = self.jobs(worker_id, page_token=page_token, **options)
            yield page
            page_token = page.get("nextPageToken")
            if not page_token:
                return

    def job(self, worker_id: str, job_id: str) -> GetWorkerJobResponseBody:
        return cast(GetWorkerJobResponseBody, self._request(OperationId.GET_WORKER_JOB,
            path={"workerId": worker_id, "jobId": job_id}))

    def check(self, worker_id: str, *, idempotency_key: str) -> CheckWorkerResponseBody:
        return cast(CheckWorkerResponseBody, self._mutation(OperationId.CHECK_WORKER, worker_id, idempotency_key))

    def maintenance(self, worker_id: str, *, idempotency_key: str) -> PlaceWorkerInMaintenanceResponseBody:
        return cast(PlaceWorkerInMaintenanceResponseBody,
            self._mutation(OperationId.PLACE_WORKER_IN_MAINTENANCE, worker_id, idempotency_key))

    def resume(self, worker_id: str, *, idempotency_key: str) -> ResumeWorkerFromMaintenanceResponseBody:
        return cast(ResumeWorkerFromMaintenanceResponseBody,
            self._mutation(OperationId.RESUME_WORKER_FROM_MAINTENANCE, worker_id, idempotency_key))

    def upgrade(self, worker_id: str, *, idempotency_key: str) -> UpgradeWorkerResponseBody:
        return cast(UpgradeWorkerResponseBody, self._mutation(OperationId.UPGRADE_WORKER, worker_id, idempotency_key))

    def operational_logs(
        self,
        worker_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        service: str | None = None,
        stream: Literal["stdout", "stderr"] | None = None,
    ) -> ListWorkerOperationalLogsResponseBody:
        return cast(ListWorkerOperationalLogsResponseBody, self._request(OperationId.LIST_WORKER_OPERATIONAL_LOGS,
            path={"workerId": worker_id}, query={
                "cursor": cursor, "limit": limit, "window": window, "since": since,
                "service": service, "stream": stream,
            }))

    def security_logs(
        self,
        worker_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        severity: Literal["debug", "info", "warn", "error"] | None = None,
        correlation_id: str | None = None,
        focus: str | None = None,
    ) -> ListWorkerSecurityLogsResponseBody:
        return cast(ListWorkerSecurityLogsResponseBody, self._request(OperationId.LIST_WORKER_SECURITY_LOGS,
            path={"workerId": worker_id}, query={
                "cursor": cursor, "limit": limit, "window": window, "since": since,
                "severity": severity, "correlationId": correlation_id, "focus": focus,
            }))

    def follow_operational_logs(
        self,
        worker_id: str,
        *,
        cancel: Event | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        service: str | None = None,
        stream: Literal["stdout", "stderr"] | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._follow(self.operational_logs, worker_id, cancel, {
            "cursor": cursor, "limit": limit, "window": window, "since": since,
            "service": service, "stream": stream,
        })

    def follow_security_logs(
        self,
        worker_id: str,
        *,
        cancel: Event | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        severity: Literal["debug", "info", "warn", "error"] | None = None,
        correlation_id: str | None = None,
        focus: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._follow(self.security_logs, worker_id, cancel, {
            "cursor": cursor, "limit": limit, "window": window, "since": since,
            "severity": severity, "correlation_id": correlation_id, "focus": focus,
        })

    def _follow(self, loader: Any, worker_id: str, cancel: Event | None, query: dict[str, Any]) -> Iterator[dict[str, Any]]:
        cursor = query.pop("cursor", None)
        last_id: int | None = None
        while cancel is None or not cancel.is_set():
            cancel_token = _REQUEST_CANCEL_EVENT.set(cancel)
            try:
                page = loader(worker_id, cursor=cursor, **query)
            except _RequestCancelled:
                return
            finally:
                _REQUEST_CANCEL_EVENT.reset(cancel_token)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                if cancel is not None and cancel.is_set():
                    return
                entry_id = int(entry["id"])
                if last_id is None or entry_id > last_id:
                    last_id = entry_id
                    yield entry
            if not page["items"]:
                if cancel is not None:
                    if cancel.wait(self._follow_interval):
                        return
                else:
                    time.sleep(self._follow_interval)

    def _mutation(self, operation: OperationId, worker_id: str, idempotency_key: str) -> Any:
        if re.fullmatch(r"[!-~]{1,128}", idempotency_key) is None:
            raise ValueError("idempotency_key must contain 1 to 128 visible ASCII characters")
        return self._request(operation, path={"workerId": worker_id}, idempotency_key=idempotency_key)

    def _request(self, operation_id: OperationId, *, path: Mapping[str, str] | None = None,
                 query: Mapping[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
        clean_query = {key: value for key, value in (query or {}).items() if value is not None}
        operation = resolve_openapi_operation(operation_id, path, clean_query)
        attempts = 3 if self._enable_retries and (operation.method == "GET" or idempotency_key) else 1
        endpoint = urljoin(self._base_url, operation.path.lstrip("/"))
        cancel_event = _REQUEST_CANCEL_EVENT.get()
        for attempt in range(1, attempts + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise _RequestCancelled
            request = Request(endpoint, method=operation.method, headers={
                "Accept": "application/json",
                **({"Authorization": f"Bearer {self._token}"} if operation.auth_lane == "worker-management" else {}),
                **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
            })
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return _decode_success(response)
            except HTTPError as error:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                api_error = _decode_http_error(error)
                if attempt < attempts and error.code in _RETRYABLE_STATUS:
                    retry_after = api_error.retry_after if error.code in {429, 503} else None
                    delay = retry_after if retry_after is not None else _jitter(attempt)
                    if cancel_event is not None:
                        if cancel_event.wait(delay):
                            raise _RequestCancelled
                    else:
                        time.sleep(delay)
                    continue
                raise api_error from None
            except URLError:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                if attempt < attempts:
                    delay = _jitter(attempt)
                    if cancel_event is not None:
                        if cancel_event.wait(delay):
                            raise _RequestCancelled
                    else:
                        time.sleep(delay)
                    continue
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                raise
        raise RuntimeError("PostGrip Worker request attempts exhausted")


class AsyncWorkerClient:
    def __init__(self, **options: Any) -> None:
        self._sync = WorkerClient(**options)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> AsyncWorkerClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_WORKER_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    async def _run(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        cancel_event = Event()
        token = _REQUEST_CANCEL_EVENT.set(cancel_event)
        try:
            return await asyncio.to_thread(callback, *args, **kwargs)
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        finally:
            _REQUEST_CANCEL_EVENT.reset(token)

    async def list(self, **options: Any) -> ListWorkersResponseBody:
        return await self._run(self._sync.list, **options)

    async def health(self) -> WorkerOrchestratorHealthResponseBody:
        return await self._run(self._sync.health)

    async def pages(self, **options: Any) -> AsyncIterator[ListWorkersResponseBody]:
        page_token = options.pop("page_token", None)
        while True:
            page = await self.list(page_token=page_token, **options)
            yield page
            page_token = page.get("nextPageToken")
            if not page_token:
                return

    async def get(self, worker_id: str) -> GetWorkerResponseBody:
        return await self._run(self._sync.get, worker_id)

    async def assignments(self, worker_id: str) -> ListWorkerAssignmentsResponseBody:
        return await self._run(self._sync.assignments, worker_id)

    async def jobs(self, worker_id: str, **options: Any) -> ListWorkerJobsResponseBody:
        return await self._run(self._sync.jobs, worker_id, **options)

    async def job_pages(self, worker_id: str, **options: Any) -> AsyncIterator[ListWorkerJobsResponseBody]:
        page_token = options.pop("page_token", None)
        while True:
            page = await self.jobs(worker_id, page_token=page_token, **options)
            yield page
            page_token = page.get("nextPageToken")
            if not page_token:
                return

    async def job(self, worker_id: str, job_id: str) -> GetWorkerJobResponseBody:
        return await self._run(self._sync.job, worker_id, job_id)

    async def check(self, worker_id: str, *, idempotency_key: str) -> CheckWorkerResponseBody:
        return await self._run(self._sync.check, worker_id, idempotency_key=idempotency_key)

    async def maintenance(self, worker_id: str, *, idempotency_key: str) -> PlaceWorkerInMaintenanceResponseBody:
        return await self._run(self._sync.maintenance, worker_id, idempotency_key=idempotency_key)

    async def resume(self, worker_id: str, *, idempotency_key: str) -> ResumeWorkerFromMaintenanceResponseBody:
        return await self._run(self._sync.resume, worker_id, idempotency_key=idempotency_key)

    async def upgrade(self, worker_id: str, *, idempotency_key: str) -> UpgradeWorkerResponseBody:
        return await self._run(self._sync.upgrade, worker_id, idempotency_key=idempotency_key)

    async def operational_logs(self, worker_id: str, **query: Any) -> ListWorkerOperationalLogsResponseBody:
        return await self._run(self._sync.operational_logs, worker_id, **query)

    async def security_logs(self, worker_id: str, **query: Any) -> ListWorkerSecurityLogsResponseBody:
        return await self._run(self._sync.security_logs, worker_id, **query)

    async def follow_operational_logs(self, worker_id: str, **query: Any) -> AsyncIterator[dict[str, Any]]:
        async for entry in self._follow(self._sync.operational_logs, worker_id, query):
            yield entry

    async def follow_security_logs(self, worker_id: str, **query: Any) -> AsyncIterator[dict[str, Any]]:
        async for entry in self._follow(self._sync.security_logs, worker_id, query):
            yield entry

    async def _follow(self, loader: Any, worker_id: str, query: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        cursor = query.pop("cursor", None)
        last_id: int | None = None
        while True:
            page = await self._run(loader, worker_id, cursor=cursor, **query)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                await asyncio.sleep(0)
                entry_id = int(entry["id"])
                if last_id is None or entry_id > last_id:
                    last_id = entry_id
                    yield entry
            if not page["items"]:
                await asyncio.sleep(self._sync._follow_interval)


def _decode_success(response: Any) -> Any:
    body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("PostGrip Worker response is too large")
    return json.loads(body) if body.strip() else None


def _decode_http_error(error: HTTPError) -> WorkerAPIError:
    body = error.read(_MAX_RESPONSE_BYTES + 1)
    try:
        value = json.loads(body) if len(body) <= _MAX_RESPONSE_BYTES else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return WorkerAPIError(
        status=error.code,
        code=value.get("code", "HTTP_ERROR"),
        message=value.get("message", error.reason or "request failed"),
        request_id=value.get("requestId", error.headers.get("X-Request-ID", "")),
        details=value.get("details") if isinstance(value.get("details"), dict) else None,
        retry_after=_parse_retry_after(error.headers.get("Retry-After")),
    )


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return min(max(float(value), 0.0), 30.0)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return min(max((when - datetime.now(timezone.utc)).total_seconds(), 0.0), 30.0)
        except (TypeError, ValueError, OverflowError):
            return None


def _jitter(attempt: int) -> float:
    return random.random() * min(0.2 * (2 ** (attempt - 1)), 2.0)
