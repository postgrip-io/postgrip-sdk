"""Sandbox platform client.

Sandboxes are persistent development environments assigned to one of your
agents. These endpoints authenticate on the *management* lane — construct the
Connection with ``auth_token`` set to a management token. An agent access token
is rejected by every endpoint here.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import IO, TYPE_CHECKING, Any

from .._internal.http import has_authorization_header
from ._sandbox_models import (  # noqa: F401 - re-exported public names
    SANDBOX_EXEC_CLOSE_STATUS_BASE,
    SANDBOX_EXEC_CLOSE_STATUS_MAX,
    SANDBOX_WORKSPACE_MAX_UPLOAD_BYTES,
    _require_sandbox_id,
    _require_workspace_id,
    sandbox_exec_exit_code,
    sandbox_is_ready,
    sandbox_relay_url,
)
from ._sandbox_transport import (  # noqa: F401 - re-exported public names
    SANDBOX_RELAY_MAX_FRAME_BYTES,
    SandboxSession,
    _same_origin_websocket_connection_factory,
    upload_archive,
)
from .openapi import (
    OperationId,
    UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REPOSITORY,
    UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REVISION,
    resolve_openapi_operation,
)
from .types import (
    CreateSandboxSessionResponse,
    Sandbox,
    SandboxCreateRequest,
    SandboxWorkspace,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._connection import Connection


class SandboxClient:
    """Sandbox lifecycle and execution."""

    def __init__(self, connection: "Connection"):
        self.connection = connection

    # --- lifecycle ---------------------------------------------------------

    def create(self, request: SandboxCreateRequest) -> Sandbox:
        """Provision a sandbox. Returns once the record exists — the sandbox is
        not yet running, so follow with :meth:`wait_until_running`."""
        return self.connection.openapi.create_sandbox(request)

    def list(self) -> list[Sandbox]:
        """List live sandboxes.

        The endpoint returns an envelope, not a bare array; decoding it as an
        array would silently yield nothing.
        """
        response = self.connection.openapi.list_sandboxes() or {}
        return response.get("sandboxes") or []

    def get(self, sandbox_id: str) -> Sandbox:
        _require_sandbox_id(sandbox_id)
        return self.connection.openapi.get_sandbox(sandbox_id)

    def start(self, sandbox_id: str) -> Sandbox:
        _require_sandbox_id(sandbox_id)
        return self.connection.openapi.start_sandbox(sandbox_id)

    def stop(self, sandbox_id: str) -> Sandbox:
        _require_sandbox_id(sandbox_id)
        return self.connection.openapi.stop_sandbox(sandbox_id)

    def delete(self, sandbox_id: str) -> Sandbox:
        _require_sandbox_id(sandbox_id)
        return self.connection.openapi.delete_sandbox(sandbox_id)

    def create_session(
        self,
        sandbox_id: str,
        *,
        kind: str = "pty",
        command: list[str] | None = None,
        rows: int | None = None,
        columns: int | None = None,
    ) -> CreateSandboxSessionResponse:
        """Mint a single-use relay ticket.

        The sandbox must already be running; while it comes up the server
        returns a retryable 400, so call :meth:`wait_until_running` first.
        """
        if kind not in ("pty", "exec"):
            raise ValueError("postgrip-agent: sandbox session kind must be 'pty' or 'exec'")
        if kind == "exec" and not command:
            raise ValueError("postgrip-agent: sandbox exec requires a command")
        body: dict[str, Any] = {"kind": kind}
        if command is not None:
            body["command"] = command
        if rows is not None:
            body["rows"] = rows
        if columns is not None:
            body["columns"] = columns
        _require_sandbox_id(sandbox_id)
        return self.connection.openapi.create_sandbox_session(sandbox_id, body)

    def upload_workspace(
        self,
        archive: bytes | IO[bytes],
        *,
        repository_name: str | None = None,
        revision: str | None = None,
    ) -> SandboxWorkspace:
        """Upload a gzipped tar archive; its ``id`` goes in ``workspaceId``.

        The body is the raw archive — not multipart. File-like inputs are sent
        incrementally with chunked transfer encoding rather than buffered in
        memory. Uploading identical bytes twice returns the *pre-existing*
        record rather than creating a second one, so do not assume a fresh id
        per upload.
        """
        headers = dict(self.connection.headers)
        headers.setdefault("User-Agent", "postgrip-agent-python")
        headers["Content-Type"] = "application/gzip"
        if self.connection.auth_token and not has_authorization_header(headers):
            headers["Authorization"] = f"Bearer {self.connection.auth_token}"
        if repository_name:
            headers[UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REPOSITORY] = repository_name
        if revision:
            headers[UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REVISION] = revision

        operation = resolve_openapi_operation(OperationId.UPLOAD_WORKSPACE)
        if not operation.streaming_request:
            raise RuntimeError("postgrip-agent: workspace upload is not a streaming OpenAPI operation")
        raw = upload_archive(
            self.connection.address + operation.path,
            operation.method,
            archive,
            headers,
            timeout=self.connection.timeout,
        )
        import json

        try:
            return json.loads(raw.decode()) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            # The body is server content, so the error names only the request.
            raise RuntimeError(f"postgrip-agent: {operation.method} {operation.path} (parse failed)") from None

    def list_workspaces(self) -> list[SandboxWorkspace]:
        """List the tenant's uploaded workspaces, newest first."""
        response = self.connection.openapi.list_workspaces() or {}
        return response.get("workspaces") or []

    def get_workspace(self, workspace_id: str) -> SandboxWorkspace:
        """Fetch one uploaded workspace by id."""
        _require_workspace_id(workspace_id)
        return self.connection.openapi.get_workspace(workspace_id)

    def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace unless a live sandbox still references it."""
        _require_workspace_id(workspace_id)
        self.connection.openapi.delete_workspace(workspace_id)

    def wait_until_running(
        self,
        sandbox_id: str,
        *,
        timeout: float = 120.0,
        poll_interval: float = 1.0,
    ) -> Sandbox:
        """Poll until the sandbox is ready, fails, or the wait expires.

        Fails fast on ``failed`` with the sandbox's own message rather than
        burning the timeout, and the timeout error names the last observed
        state — "timed out" alone does not say whether the sandbox was still
        scheduling, mid-setup, or never picked up by an agent.
        """
        deadline = time.monotonic() + timeout
        last: Mapping[str, Any] = {}
        while True:
            record = self.get(sandbox_id)
            last = record
            if sandbox_is_ready(record):
                return record
            if record.get("observedState") == "failed":
                detail = (
                    record.get("failureMessage")
                    or record.get("failureCode")
                    or "no failure detail reported"
                )
                raise RuntimeError(f"postgrip-agent: sandbox {sandbox_id} failed: {detail}")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"postgrip-agent: sandbox {sandbox_id} was not running within {timeout}s "
                    f"(last observed state: {last.get('observedState', 'unknown')})"
                )
            # Never sleep past the deadline. An unclamped sleep meant a
            # poll_interval larger than the time remaining postponed the next
            # deadline check by the whole interval — `timeout=5,
            # poll_interval=60` blocked for about a minute before raising, so
            # the timeout this call advertises was not the one it kept.
            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

    # --- sessions ----------------------------------------------------------

    def open_session(
        self,
        sandbox_id: str,
        *,
        kind: str = "pty",
        command: list[str] | None = None,
        rows: int | None = None,
        columns: int | None = None,
        relay_base_url: str | None = None,
    ) -> "SandboxSession":
        """Create a session and dial the relay.

        Requires the optional ``websockets`` dependency::

            pip install "postgrip[sandbox]"
        """
        relay_address = relay_base_url or self.connection.address
        # Validate the transport before creating a single-use session ticket.
        sandbox_relay_url(
            relay_address,
            "validation",
            "validation",
            insecure_development=self.connection.insecure_development,
        )
        session = self.create_session(
            sandbox_id, kind=kind, command=command, rows=rows, columns=columns
        )
        url = sandbox_relay_url(
            relay_address,
            session["id"],
            session["ticket"],
            insecure_development=self.connection.insecure_development,
        )
        # Start from the connection's configured headers rather than only its
        # auth_token. A caller authenticating through
        # `Connection(headers={"Authorization": ...})` — a supported way to do
        # it, and the way a header-authenticating gateway is fed — got an
        # unauthenticated relay dial, so session creation succeeded and the
        # dial failed *after* burning the single-use ticket.
        headers = dict(self.connection.headers)
        if self.connection.auth_token and not has_authorization_header(headers):
            # The ticket authorizes the session; the management credential
            # still authenticates the request. Both are required.
            headers["Authorization"] = f"Bearer {self.connection.auth_token}"
        return SandboxSession(url, headers)

    def exec(
        self,
        sandbox_id: str,
        command: list[str],
        *,
        stdin: bytes | None = None,
        relay_base_url: str | None = None,
    ) -> tuple[int | None, bytes]:
        """Run a command and return ``(exit_code, output)``.

        ``output`` carries stdout and stderr *interleaved* — the relay is a
        single stream, so they cannot be separated client-side. ``exit_code``
        is ``None`` when the close carried no code, meaning the transport ended
        rather than the process.

        After sending ``stdin`` (or immediately when it is ``None``), the SDK
        signals end-of-stdin while leaving output open. Commands that read to
        EOF, such as ``cat``, ``sort``, and archive imports, can therefore
        finish normally and still report their exit status.
        """
        session = self.open_session(
            sandbox_id, kind="exec", command=command, relay_base_url=relay_base_url
        )
        with session:
            if stdin:
                session.send(stdin)
            session.close_input()
            chunks = list(session.read_all())
            return session.exit_code, b"".join(chunks)
