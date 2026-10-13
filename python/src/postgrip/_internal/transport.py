"""The contract-driven executor shared by the Python planes.

It runs one resolved generated operation under the contract's auth-lane,
idempotency, retry, response-bound and error-envelope rules. Plane
differences are configuration, never copies of this loop.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import random
import re
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, HTTPSHandler, OpenerDirector, Request, build_opener

from .config import validate_idempotency_key
from .http import (
    REQUEST_CANCEL_EVENT,
    CancellationAwareHTTPHandler,
    CancellationAwareHTTPSHandler,
    RequestCancelled,
    read_bounded_response,
)

DEFAULT_MAX_RESPONSE_BYTES = 4 << 20
RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})
_MANAGEMENT_LANES = frozenset({"management", "worker-management", "service-management"})


@dataclass(frozen=True)
class PostGripAPIError(Exception):
    """The decoded common error envelope. Plane errors subclass it."""

    status: int
    code: str
    message: str
    request_id: str = ""
    details: Mapping[str, Any] | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        return f"postgrip: {self.code} (HTTP {self.status}): {self.message}"


@dataclass(frozen=True)
class APIErrorFields:
    """One failed exchange, from which a plane builds its typed error.

    ``message`` is the envelope message or the reason phrase and
    ``response_body`` the bounded raw body; both are server content.
    """

    status: int
    code: str
    message: str
    request_id: str
    details: Mapping[str, Any] | None
    retry_after: float | None
    method: str
    route: str
    response_body: bytes


class TransportOperation(Protocol):
    """The contract annotations of one resolved generated operation."""

    @property
    def operation_id(self) -> Any: ...
    @property
    def method(self) -> str: ...
    @property
    def path(self) -> str: ...
    @property
    def auth_lane(self) -> str: ...
    @property
    def safety(self) -> str: ...
    @property
    def retry(self) -> str: ...
    @property
    def signing(self) -> str: ...
    @property
    def streaming_request(self) -> bool: ...
    @property
    def websocket(self) -> bool: ...
    @property
    def idempotency(self) -> str: ...
    @property
    def header_parameters(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class RetryConfig:
    enabled: bool
    max_attempts: int
    max_delay: float
    retry_after_max: float


class Executor:
    """Runs generated operations under their contract annotations."""

    def __init__(
        self,
        *,
        plane: str,
        base_url: str,
        opener: OpenerDirector,
        management_token: str,
        retry: RetryConfig,
        timeout: float,
        create_error: Callable[[APIErrorFields], Exception],
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        success_response_bytes: Mapping[str, int] | None = None,
    ) -> None:
        self._plane = plane
        self._base_url = base_url.rstrip("/") + "/"
        self._opener = opener
        self._management_token = management_token
        self._retry = retry
        self._timeout = timeout
        self._create_error = create_error
        self._max_response_bytes = max_response_bytes
        self._success_response_bytes = dict(success_response_bytes or {})

    @property
    def opener(self) -> OpenerDirector:
        return self._opener

    def request(
        self,
        operation: TransportOperation,
        *,
        body: Any = None,
        idempotency_key: str | None = None,
        if_match: str | None = None,
    ) -> Any:
        """Run one operation and decode its JSON body; an empty body returns None."""

        operation_id = getattr(operation.operation_id, "value", operation.operation_id)
        if operation.streaming_request or operation.websocket:
            raise ValueError(f"PostGrip {self._plane} operation {operation_id} requires its protocol adapter")
        if operation.signing:
            raise ValueError(f"PostGrip {self._plane} operation {operation_id} requires request signing")
        if operation.auth_lane not in _MANAGEMENT_LANES and operation.auth_lane != "public":
            raise ValueError(
                f"PostGrip {self._plane} operation {operation_id} uses unsupported auth lane {operation.auth_lane}"
            )
        if operation.idempotency == "required":
            validate_idempotency_key(idempotency_key or "")

        endpoint = urljoin(self._base_url, operation.path.lstrip("/"))
        encoded_body = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json"}
        if encoded_body is not None:
            headers["Content-Type"] = "application/json"
        if operation.auth_lane in _MANAGEMENT_LANES:
            headers["Authorization"] = f"Bearer {self._management_token}"
        if idempotency_key and "Idempotency-Key" in operation.header_parameters:
            headers["Idempotency-Key"] = idempotency_key
        if if_match and "If-Match" in operation.header_parameters:
            headers["If-Match"] = if_match

        retry = self._retry
        # Protocol and signed operations are never retried, even if mis-annotated as bounded.
        eligible = (
            retry.enabled
            and operation.retry == "bounded"
            and operation.safety != "protocol"
            and not operation.signing
            and (operation.safety == "read-only" or bool(idempotency_key))
        )
        attempts = retry.max_attempts if eligible else 1
        cancel_event = REQUEST_CANCEL_EVENT.get()
        for attempt in range(1, attempts + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise RequestCancelled
            request = Request(endpoint, data=encoded_body, method=operation.method, headers=headers)
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    limit = self._success_response_bytes.get(str(operation_id), self._max_response_bytes)
                    raw = read_bounded_response(response, self._plane, maximum_bytes=limit)
                    return json.loads(raw) if raw.strip() else None
            except HTTPError as error:
                if cancel_event is not None and cancel_event.is_set():
                    raise RequestCancelled from None
                fields = self._decode_error(operation, error)
                if attempt < attempts and error.code in RETRYABLE_STATUS:
                    retry_after = fields.retry_after if error.code in {429, 503} else None
                    self._wait(retry_after if retry_after is not None else jitter(attempt, retry.max_delay))
                    continue
                raise self._create_error(fields) from None
            except URLError:
                if cancel_event is not None and cancel_event.is_set():
                    raise RequestCancelled from None
                if attempt < attempts:
                    self._wait(jitter(attempt, retry.max_delay))
                    continue
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set():
                    raise RequestCancelled from None
                raise
        raise RuntimeError(f"PostGrip {self._plane} request attempts exhausted")

    def _decode_error(self, operation: TransportOperation, error: HTTPError) -> APIErrorFields:
        try:
            body = read_bounded_response(error, self._plane, maximum_bytes=self._max_response_bytes)
        except ValueError:
            body = b""
        finally:
            error.close()
        return api_error_fields(
            error.code,
            error.reason,
            error.headers,
            body,
            operation.method,
            operation.path,
            self._retry.retry_after_max,
        )

    def _wait(self, delay: float) -> None:
        cancel_event = REQUEST_CANCEL_EVENT.get()
        if cancel_event is not None:
            if cancel_event.wait(delay):
                raise RequestCancelled
        else:
            time.sleep(delay)


def api_error_fields(
    status: int,
    reason: Any,
    headers: Any,
    body: bytes,
    method: str,
    route: str,
    retry_after_max: float,
) -> APIErrorFields:
    """Decode the common error envelope, falling back to HTTP_ERROR and the reason phrase."""

    try:
        value = json.loads(body) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    code = value.get("code")
    message = value.get("message")
    request_id = value.get("requestId")
    details = value.get("details")
    return APIErrorFields(
        status=status,
        code=code if isinstance(code, str) else "HTTP_ERROR",
        message=message if isinstance(message, str) else (str(reason) if reason else "request failed"),
        request_id=request_id if isinstance(request_id, str) else (headers.get("X-Request-ID", "") if headers else ""),
        details=details if isinstance(details, dict) else None,
        retry_after=parse_retry_after(headers.get("Retry-After") if headers else None, retry_after_max),
        method=method,
        route=route,
        response_body=body,
    )


def parse_retry_after(value: str | None, maximum: float) -> float | None:
    """Parse non-negative delta-seconds or an HTTP date, capped at ``maximum``.

    A signed, fractional or otherwise invalid value is ignored, so the jittered
    backoff applies.
    """

    trimmed = (value or "").strip()
    if not trimmed:
        return None
    if re.fullmatch(r"\d+", trimmed):
        return min(float(trimmed), maximum)
    if not re.search(r"[A-Za-z]", trimmed):
        return None
    try:
        when = parsedate_to_datetime(trimmed)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return min(max((when - datetime.now(timezone.utc)).total_seconds(), 0.0), maximum)


def jitter(attempt: int, maximum: float) -> float:
    return random.random() * min(0.2 * (2 ** (attempt - 1)), maximum)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def no_redirect_opener(opener: OpenerDirector | None) -> OpenerDirector:
    """An opener that returns every 3xx as an error and supports request cancellation.

    A caller-supplied opener keeps its other handlers and HTTPS context.
    """

    https_context = None
    https_check_hostname = None
    if opener is not None:
        for handler in opener.handlers:
            if isinstance(handler, HTTPSHandler):
                https_context = getattr(handler, "_context", None)
                https_check_hostname = getattr(handler, "_check_hostname", None)
                break
    cancellation_handlers = (
        CancellationAwareHTTPHandler(),
        CancellationAwareHTTPSHandler(context=https_context, check_hostname=https_check_hostname),
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
