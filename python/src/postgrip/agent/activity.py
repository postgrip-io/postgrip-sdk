from __future__ import annotations

import contextvars
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar, overload

from ._events import milestone_event
from .errors import CancelledFailure, is_terminal_task_mutation

F = TypeVar("F", bound=Callable[..., Any])
R = TypeVar("R")


@dataclass(frozen=True)
class ActivityInfo:
    task_id: str
    activity_type: str


@dataclass
class _ActivityRuntime:
    task_id: str
    activity_type: str
    heartbeat: Callable[[dict[str, Any] | None], Awaitable[None]]
    emit: Callable[[dict[str, Any]], Awaitable[None]]


_activity_runtime: contextvars.ContextVar[_ActivityRuntime | None] = contextvars.ContextVar("postgrip_activity_runtime", default=None)


@overload
def defn(fn: F, /) -> F:
    ...


@overload
def defn(fn: None = None, /, *, name: str | None = None) -> Callable[[F], F]:
    ...


def defn(fn: F | None = None, /, *, name: str | None = None) -> F | Callable[[F], F]:
    def decorate(target: F) -> F:
        setattr(target, "_postgrip_activity_name", name or target.__name__)
        return target

    if fn is not None:
        return decorate(fn)
    return decorate


def activity_name(fn: Callable[..., Any]) -> str:
    return str(getattr(fn, "_postgrip_activity_name", fn.__name__))


def info() -> ActivityInfo:
    runtime = _activity_runtime.get()
    if runtime is None:
        raise RuntimeError("activity.info() called outside of a PostGrip activity runtime")
    return ActivityInfo(task_id=runtime.task_id, activity_type=runtime.activity_type)


async def heartbeat(details: dict[str, Any] | None = None) -> None:
    runtime = _activity_runtime.get()
    if runtime is None:
        raise RuntimeError("activity.heartbeat() called outside of a PostGrip activity runtime")
    try:
        await runtime.heartbeat(details)
    except Exception as exc:
        if is_terminal_task_mutation(exc):
            raise CancelledFailure("activity cancellation requested") from exc
        raise


async def milestone(
    name: str,
    *,
    index: int | None = None,
    total: int | None = None,
    status: str = "completed",
    details: dict[str, Any] | None = None,
) -> None:
    runtime = _activity_runtime.get()
    if runtime is None:
        raise RuntimeError("activity.milestone() called outside of a PostGrip activity runtime")
    await runtime.emit(milestone_event(
        name, index=index, total=total, status=status, details=details,
    ))


async def stdout(
    data: str,
    *,
    stage: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    await _emit_output("stdout", data, stage=stage, message=message, details=details)


async def stderr(
    data: str,
    *,
    stage: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    await _emit_output("stderr", data, stage=stage, message=message, details=details)


async def run_in_activity_runtime(runtime: _ActivityRuntime, fn: Callable[[], R | Awaitable[R]]) -> R:
    token = _activity_runtime.set(runtime)
    try:
        value = fn()
        if inspect.isawaitable(value):
            return await value
        return value
    finally:
        _activity_runtime.reset(token)


async def _emit_output(
    stream: str,
    data: str,
    *,
    stage: str | None,
    message: str | None,
    details: dict[str, Any] | None,
) -> None:
    runtime = _activity_runtime.get()
    if runtime is None:
        raise RuntimeError(f"activity.{stream}() called outside of a PostGrip activity runtime")
    await runtime.emit({
        "kind": stream,
        "stage": stage or "activity",
        "message": message,
        "stream": stream,
        "data": data,
        "details": dict(details or {}),
    })


__all__ = [
    "ActivityInfo",
    "activity_name",
    "defn",
    "heartbeat",
    "info",
    "milestone",
    "run_in_activity_runtime",
    "stderr",
    "stdout",
]
