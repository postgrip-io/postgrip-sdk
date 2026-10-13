from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json

from .._internal.transport import APIErrorFields, PostGripAPIError


class PostGripAgentError(Exception):
    pass


class ApplicationFailure(PostGripAgentError):
    def __init__(self, message: str, *, type: str = "ApplicationFailure", non_retryable: bool = False, details=None):
        super().__init__(message)
        self.type = type
        self.non_retryable = non_retryable
        self.details = list(details or [])

    @classmethod
    def non_retryable_failure(cls, message: str, type: str = "NonRetryableFailure", *details):
        return cls(message, type=type, non_retryable=True, details=details)


class CancelledFailure(PostGripAgentError):
    pass


class TaskFailedError(PostGripAgentError):
    def __init__(self, task_id: str, message: str):
        super().__init__(message)
        self.task_id = task_id


class TimeoutFailure(PostGripAgentError):
    pass


@dataclass(frozen=True, repr=False)
class AgentAPIError(PostGripAPIError, RuntimeError):
    """A failed Agent HTTP exchange.

    Its text and repr name only the method, route and status, never server
    content. ``code``, ``message``, ``request_id``, ``details`` and the raw
    ``response_body`` are server-provided; redact them before logging. It stays
    a ``RuntimeError`` so existing handlers still match.
    """

    method: str = ""
    route: str = ""
    response_body: bytes = b""

    @classmethod
    def _from_fields(cls, fields: APIErrorFields) -> AgentAPIError:
        return cls(
            status=fields.status,
            code=fields.code,
            message=fields.message,
            request_id=fields.request_id,
            details=fields.details,
            retry_after=fields.retry_after,
            method=fields.method,
            route=fields.route,
            response_body=fields.response_body,
        )

    def __str__(self) -> str:
        try:
            phrase = HTTPStatus(self.status).phrase
        except ValueError:
            phrase = ""
        return f"postgrip-agent: {json.dumps(self.method)} {json.dumps(self.route)} -> {self.status} {phrase}".rstrip()

    def __repr__(self) -> str:
        return f"AgentAPIError(status={self.status!r}, method={self.method!r}, route={self.route!r})"


def is_terminal_task_mutation(exc: BaseException) -> bool:
    """Whether a task mutation failed because the task is already terminal or no
    longer leased. The server reports both as a 409 whose envelope message names
    the condition."""
    if isinstance(exc, AgentAPIError):
        message = exc.message if exc.status == 409 else ""
    else:
        message = str(exc)
    return "terminal" in message or "not leased" in message
