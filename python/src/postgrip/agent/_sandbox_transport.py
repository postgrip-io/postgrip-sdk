"""Sandbox protocol adapters: the relay WebSocket session and archive upload."""

from __future__ import annotations

from collections.abc import Iterable
from typing import IO, Any
from urllib.error import HTTPError
from urllib.request import Request

from .._internal.http import read_bounded_response, redirect_safe_open as urlopen
from ._sandbox_models import sandbox_exec_exit_code

#: Bound on a single frame through the session relay, in either direction. A
#: peer writing more has its session closed rather than forwarded, so chunk
#: writes at or below this.
SANDBOX_RELAY_MAX_FRAME_BYTES = 1 << 20

class SandboxSession:
    """A live sandbox session: a raw bidirectional byte stream.

    Message boundaries are opaque except for the reserved zero-length binary
    stdin-EOF message sent by :meth:`close_input`. There is no resize channel;
    rows and columns are fixed when the session is created.
    """

    def __init__(self, url: str, headers: dict[str, str]):
        try:
            from websockets.sync.client import (  # type: ignore[import-not-found]
                ClientConnection,
                connect,
            )
            from websockets.uri import parse_uri  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "postgrip-agent: sandbox sessions need the 'websockets' package; "
                'install with pip install "postgrip[sandbox]"'
            ) from exc
        self._socket = connect(
            url,
            additional_headers=headers,
            max_size=None,
            create_connection=_same_origin_websocket_connection_factory(
                url, ClientConnection, parse_uri
            ),
        )
        self.exit_code: int | None = None
        self._input_closed = False

    def send(self, data: bytes | str) -> None:
        if self._input_closed:
            raise RuntimeError("postgrip-agent: sandbox session input is closed")
        payload = data.encode() if isinstance(data, str) else data
        size = len(payload)
        # Empty binary messages carry the stdin-EOF control. Keep an empty
        # send as a byte-stream no-op; close_input owns the control message.
        if size == 0:
            return
        if size > SANDBOX_RELAY_MAX_FRAME_BYTES:
            raise ValueError(
                f"postgrip-agent: sandbox write of {size} bytes exceeds the relay frame "
                f"limit ({SANDBOX_RELAY_MAX_FRAME_BYTES}); chunk your writes"
            )
        self._socket.send(payload)

    def close_input(self) -> None:
        """Signal stdin EOF without closing output or exit-status delivery."""
        if self._input_closed:
            return
        try:
            self._socket.send(b"")
        except Exception as exc:
            # A command that never reads stdin can close with its valid exit
            # status before this empty EOF frame is written. Preserve that
            # process result; closes without an exec status remain failures.
            received = getattr(exc, "rcvd", None)
            close_code = getattr(received, "code", None)
            if close_code is None:
                close_code = getattr(self._socket, "close_code", None)
            exit_code = sandbox_exec_exit_code(close_code) if isinstance(close_code, int) else None
            if exit_code is None:
                raise
            self.exit_code = exit_code
        self._input_closed = True

    def read_all(self) -> Iterable[bytes]:
        """Yield output until the session closes, recording the exit code."""
        from websockets.exceptions import ConnectionClosed  # type: ignore[import-not-found]

        try:
            for message in self._socket:
                yield message if isinstance(message, bytes) else message.encode()
        except ConnectionClosed as exc:
            self.exit_code = sandbox_exec_exit_code(exc.rcvd.code if exc.rcvd else 0)
        else:
            close_code = getattr(self._socket, "close_code", None)
            if close_code is not None:
                self.exit_code = sandbox_exec_exit_code(close_code)

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "SandboxSession":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _same_origin_websocket_connection_factory(
    trusted_url: str,
    connection_type: type[Any],
    parse_uri: Any,
) -> Any:
    """Reject a relay redirect before its handshake can send credentials.

    websockets 15+ follows handshake redirects. Its default cross-origin
    handling strips a small set of standard credentials, but arbitrary
    configured gateway headers remain attached. The connection factory is
    invoked after the destination URI is parsed and before the handshake is
    written, which makes it the earliest version-compatible enforcement point
    across the supported websockets>=13 range.
    """
    trusted = parse_uri(trusted_url)
    trusted_origin = (trusted.secure, trusted.host, trusted.port)

    def create_connection(sock: Any, protocol: Any, **kwargs: Any) -> Any:
        candidate = getattr(protocol, "uri", None)
        if candidate is None:
            candidate = getattr(protocol, "wsuri", None)
        candidate_origin = (
            getattr(candidate, "secure", None),
            getattr(candidate, "host", None),
            getattr(candidate, "port", None),
        )
        if candidate_origin != trusted_origin:
            raise RuntimeError(
                "postgrip-agent: refusing cross-origin sandbox relay redirect"
            )
        return connection_type(sock, protocol, **kwargs)

    return create_connection


def upload_archive(
    url: str,
    method: str,
    archive: bytes | IO[bytes],
    headers: dict[str, str],
    *,
    timeout: float | None,
) -> bytes:
    """Send a workspace archive as the raw request body and return the bounded response."""
    request = Request(
        url,
        # urllib/http.client streams file-like request bodies in blocks.
        # When their length is unknown it selects chunked transfer encoding.
        data=archive,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = read_bounded_response(response, "Agent")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    except HTTPError as exc:
        try:
            raw = read_bounded_response(exc, "Agent")
        except ValueError as read_error:
            raise RuntimeError(str(read_error)) from exc
        finally:
            exc.close()
        raise RuntimeError(raw.decode() or str(exc)) from exc
    return raw
