from __future__ import annotations

import asyncio
from contextvars import ContextVar
from http.client import HTTPConnection, HTTPSConnection
import socket
from threading import Event, Thread
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, OpenerDirector, Request, build_opener

_MAX_RESPONSE_BYTES = 4 << 20

# The cancellation event for the request running in the current thread. Set by
# run_cancellable, or by a synchronous follower around one page request.
REQUEST_CANCEL_EVENT: ContextVar[Event | None] = ContextVar("postgrip_request_cancel", default=None)


class SafeRedirectHandler(HTTPRedirectHandler):
    """Follow same-origin redirects but refuse cross-origin redirects."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        target = urljoin(req.full_url, newurl)
        if _origin(req.full_url) != _origin(target):
            return None
        return super().redirect_request(req, fp, code, msg, headers, target)


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80 if parsed.scheme.lower() == "http" else None
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


_REDIRECT_SAFE_OPENER: OpenerDirector = build_opener(SafeRedirectHandler())


def redirect_safe_open(request: Request, timeout: float | None = None) -> Any:
    """Open one request without following a redirect to another origin."""

    return _REDIRECT_SAFE_OPENER.open(request, timeout=timeout)


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


class ResponseTooLarge(ValueError):
    """A response body exceeded its plane bound."""


def read_bounded_response(
    source: Any,
    plane: str,
    *,
    maximum_bytes: int = _MAX_RESPONSE_BYTES,
) -> bytes:
    """Read a response without exceeding the selected plane bound."""

    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    while remaining > 0:
        chunk = source.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > maximum_bytes:
        raise ResponseTooLarge(f"PostGrip {plane} response is invalid or too large")
    return body


class RequestCancelled(Exception):
    """Raised inside a plane request loop when its cancellation event is set."""


class _CancellationAwareConnection:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cancel_event = REQUEST_CANCEL_EVENT.get()
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


class CancellationAwareHTTPHandler(HTTPHandler):
    handler_order = 400

    def http_open(self, request: Request) -> Any:
        return self.do_open(_CancellationAwareHTTPConnection, request)


class CancellationAwareHTTPSHandler(HTTPSHandler):
    handler_order = 400

    def https_open(self, request: Request) -> Any:
        # Python 3.12 removed HTTPSConnection's check_hostname argument and
        # HTTPSHandler's _check_hostname attribute (it now applies the setting
        # to the context). Forward it only where the running stdlib keeps it.
        options: dict[str, Any] = {"context": getattr(self, "_context", None)}
        check_hostname = getattr(self, "_check_hostname", None)
        if check_hostname is not None:
            options["check_hostname"] = check_hostname
        return self.do_open(_CancellationAwareHTTPSConnection, request, **options)


async def run_cancellable(callback: Any, *args: Any, **kwargs: Any) -> Any:
    """Run blocking request code in a thread; cancelling the caller closes its socket."""

    cancel_event = Event()
    token = REQUEST_CANCEL_EVENT.set(cancel_event)
    try:
        return await asyncio.to_thread(callback, *args, **kwargs)
    except asyncio.CancelledError:
        cancel_event.set()
        raise
    finally:
        REQUEST_CANCEL_EVENT.reset(token)
