"""Pure sandbox transformations: relay URLs, exit codes and readiness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .openapi import (
    CONNECT_SANDBOX_SESSION_PATH_SESSION_ID,
    CONNECT_SANDBOX_SESSION_QUERY_TICKET,
    OperationId,
    resolve_openapi_operation,
)

#: Exec exit codes arrive as the WebSocket close status, ``4000 + code``. A
#: close outside this range is a transport failure, not a process exit.
SANDBOX_EXEC_CLOSE_STATUS_BASE = 4000
SANDBOX_EXEC_CLOSE_STATUS_MAX = SANDBOX_EXEC_CLOSE_STATUS_BASE + 255

#: Server cap on a workspace archive upload; larger uploads are rejected 413.
SANDBOX_WORKSPACE_MAX_UPLOAD_BYTES = 512 << 20


def sandbox_exec_exit_code(close_status: int) -> int | None:
    """Decode a process exit code from a WebSocket close status.

    Returns ``None`` when the status carried no exit code — that means the
    transport ended rather than the process, and must not be read as success.
    """
    if close_status < SANDBOX_EXEC_CLOSE_STATUS_BASE or close_status > SANDBOX_EXEC_CLOSE_STATUS_MAX:
        return None
    return close_status - SANDBOX_EXEC_CLOSE_STATUS_BASE


def sandbox_relay_url(
    base_url: str,
    session_id: str,
    ticket: str,
    *,
    insecure_development: bool = False,
) -> str:
    """Build the ``ws(s)://`` relay URL from an ``http(s)`` API base URL."""
    base = base_url.strip().rstrip("/")
    # URL schemes are case-insensitive (RFC 3986 §3.1), and urllib accepts
    # `HTTPS://…` for every other request this SDK makes. Matching the literal
    # prefix rejected an address that works everywhere else, which made opening
    # a session the single operation a mixed-case address broke.
    scheme, separator, remainder = base.partition("://")
    scheme = scheme.lower()
    if separator and scheme == "https":
        origin = "wss://" + remainder
    elif separator and scheme == "http":
        if not insecure_development:
            raise ValueError("postgrip-agent: sandbox relay base must use WSS unless insecure_development is enabled")
        origin = "ws://" + remainder
    elif separator and scheme == "wss":
        origin = f"{scheme}://{remainder}"
    elif separator and scheme == "ws":
        if not insecure_development:
            raise ValueError("postgrip-agent: sandbox relay base must use WSS unless insecure_development is enabled")
        origin = f"{scheme}://{remainder}"
    else:
        raise ValueError(f"postgrip-agent: sandbox relay base must be http(s) or ws(s): {base_url}")
    operation = resolve_openapi_operation(
        OperationId.CONNECT_SANDBOX_SESSION,
        {CONNECT_SANDBOX_SESSION_PATH_SESSION_ID: session_id},
        {CONNECT_SANDBOX_SESSION_QUERY_TICKET: ticket},
    )
    return origin + operation.path


def sandbox_is_ready(record: Mapping[str, Any]) -> bool:
    """Readiness is observed state AND generation.

    A ``running`` reading can predate a start or stop the assigned agent has
    not observed yet, so state alone can describe a sandbox that is about to
    change again.
    """
    return record.get("observedState") == "running" and _observes_current_generation(record)


def _sandbox_failed(record: Mapping[str, Any]) -> bool:
    """A ``failed`` reading at the current generation.

    A ``failed`` left over from the previous generation does not describe a
    just-issued start, so it is not a failure of the wait.
    """
    return record.get("observedState") == "failed" and _observes_current_generation(record)


def _observes_current_generation(record: Mapping[str, Any]) -> bool:
    return int(record.get("observedGeneration") or 0) >= int(record.get("generation") or 0)


def _require_sandbox_id(sandbox_id: str) -> None:
    if not sandbox_id:
        # Otherwise this builds /api/v1/sandboxes/ and hits the collection
        # route, which is a confusing 404 or worse a list.
        raise ValueError("postgrip-agent: sandbox id is required")


def _require_workspace_id(workspace_id: str) -> None:
    if not workspace_id:
        raise ValueError("postgrip-agent: workspace id is required")
