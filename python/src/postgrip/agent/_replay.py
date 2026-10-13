"""Durable-history replay for the Agent workflow runtime.

Replay walks the history a workflow task fetched and serves recorded commands
back to the workflow body. It owns ``DeterminismError`` and depends on no SDK
failure type; the Agent translates the error at its runtime boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


class DeterminismError(Exception):
    """Workflow code disagreed with durable history."""


_COMMAND_TYPES = frozenset({"ActivityTaskScheduled", "TimerStarted", "ChildWorkflowExecutionStarted"})
_UPDATE_ACCEPTED = "WorkflowUpdateAccepted"
_UPDATE_TERMINAL_TYPES = frozenset({"WorkflowUpdateCompleted", "WorkflowUpdateFailed"})


@dataclass
class _CommandCursor:
    """One owner's ordered position over its command events."""

    events: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    next: int = 0
    activities: int = 0
    timers: int = 0
    children: int = 0


def ownership_candidates(history: Sequence[Mapping[str, Any]]) -> list[str]:
    """Task IDs of the command events that could belong to an update.

    Those are the events between an accepted update event and its terminal
    event, or the end of history while it is pending, and those before the
    terminal event of a legacy entry with no accepted event. The Agent reads
    each one's owner before building a replay.
    """
    accepted_at: dict[str, int] = {}
    terminal_at: dict[str, int] = {}
    for index, event in enumerate(history):
        task_id = event.get("task_id")
        if not task_id:
            continue
        if event.get("type") == _UPDATE_ACCEPTED:
            accepted_at.setdefault(task_id, index)
        elif event.get("type") in _UPDATE_TERMINAL_TYPES:
            terminal_at.setdefault(task_id, index)

    def in_window(index: int) -> bool:
        for task_id, terminal in terminal_at.items():
            if accepted_at.get(task_id, -1) < index < terminal:
                return True
        return any(task_id not in terminal_at and index > start for task_id, start in accepted_at.items())

    candidates: dict[str, None] = {}
    for index, event in enumerate(history):
        task_id = event.get("task_id")
        if event.get("type") in _COMMAND_TYPES and task_id and in_window(index):
            candidates.setdefault(task_id, None)
    return list(candidates)


class WorkflowReplay:
    def __init__(self, history: list[dict[str, Any]], owners: Mapping[str, str] | None = None):
        """Build replay state from history and the command owners the Agent read.

        *owners* maps a command event's ``task_id`` to the task that issued it;
        a command missing from it belongs to the body.
        """
        self.history = history
        owners = owners or {}
        update_tasks = {
            event.get("task_id")
            for event in history
            if event.get("task_id") and (event.get("type") == _UPDATE_ACCEPTED or event.get("type") in _UPDATE_TERMINAL_TYPES)
        }
        # Body-owned command events in history order; the body must consume them in this order.
        self._body = _CommandCursor()
        # Command events each update task owns, in history order.
        self._owned: dict[str, _CommandCursor] = {}
        for index, event in enumerate(history):
            if event.get("type") not in _COMMAND_TYPES:
                continue
            owner = owners.get(event.get("task_id") or "")
            if owner and owner in update_tasks:
                self._owned.setdefault(owner, _CommandCursor()).events.append((index, event))
            else:
                self._body.events.append((index, event))
        # The executing update task, or None while the body runs.
        self._owner: str | None = None
        self._owner_live = False
        self.signals = [event for event in history if event.get("type") == "WorkflowSignaled"]
        self.completed_updates = [event for event in history if event.get("type") == "WorkflowUpdateCompleted"]
        self.cancellation = next((event for event in history if event.get("type") == "WorkflowCancellationRequested"), None)
        # The first determinism error raised; a caught one still fails the task.
        self.determinism_error: DeterminismError | None = None

    def next_activity(self, activity_type: str) -> dict[str, Any] | None:
        cursor = self._current()
        event = self._next_command("ActivityTaskScheduled")
        if event and (event.get("attributes") or {}).get("activity_type") != activity_type:
            raise self._fail(f"activity command changed at index {cursor.activities + 1}: history={(event.get('attributes') or {}).get('activity_type')} replay={activity_type}")
        if event:
            cursor.activities += 1
            cursor.next += 1
        return event

    def next_timer(self, duration_ms: int | None = None) -> dict[str, Any] | None:
        cursor = self._current()
        event = self._next_command("TimerStarted")
        history_duration = (event.get("attributes") or {}).get("duration_ms") if event else None
        if event and duration_ms is not None and history_duration is not None and round(duration_ms) != history_duration:
            raise self._fail(f"timer command changed at index {cursor.timers + 1}: history={history_duration} replay={round(duration_ms)}")
        if event:
            cursor.timers += 1
            cursor.next += 1
        return event

    def next_child(self, workflow_type: str) -> dict[str, Any] | None:
        cursor = self._current()
        event = self._next_command("ChildWorkflowExecutionStarted")
        if event and (event.get("attributes") or {}).get("workflow_type") != workflow_type:
            raise self._fail(f"child workflow command changed at index {cursor.children + 1}: history={(event.get('attributes') or {}).get('workflow_type')} replay={workflow_type}")
        if event:
            cursor.children += 1
            cursor.next += 1
        return event

    def enter_owner(self, task_id: str, live: bool) -> Callable[[], None]:
        """Make the update task the executing owner until the returned callable restores the previous one.

        A live owner schedules new commands once its recorded ones are consumed;
        a replayed owner already finished, so a further command is a
        determinism error.
        """
        previous, previous_live = self._owner, self._owner_live
        self._owner, self._owner_live = task_id, live

        def restore() -> None:
            self._owner, self._owner_live = previous, previous_live

        return restore

    def check_body_consumed(self) -> None:
        """The completion check's leftover test.

        A body-owned command event left unconsumed when the workflow completes,
        continues as new or, in query replay, returns, is a recorded
        determinism error.
        """
        self._check_consumed(self._body, "workflow")

    def check_owner_consumed(self, task_id: str) -> None:
        """Fail a replayed update handler that returned or raised with its own command events left unconsumed."""
        cursor = self._owned.get(task_id)
        if cursor is not None:
            self._check_consumed(cursor, f"update {task_id} handler")

    def _check_consumed(self, cursor: _CommandCursor, who: str) -> None:
        if cursor.next < len(cursor.events):
            index, event = cursor.events[cursor.next]
            raise self._fail(f"{who} finished before replaying recorded command at history index {index}: history={event.get('type')}")

    def _current(self) -> _CommandCursor:
        if self._owner is None:
            return self._body
        return self._owned.setdefault(self._owner, _CommandCursor())

    def _next_command(self, kind: str) -> dict[str, Any] | None:
        """The executing owner's earliest unconsumed command event, without consuming it.

        ``None`` when none remains (the command is new). A different kind is a
        determinism error, covering reordering and a kind whose events ran out
        while others remain. A replayed update handler with no recorded command
        left has already finished, so a further command is a determinism error.
        """
        cursor = self._current()
        if cursor.next >= len(cursor.events):
            if self._owner is not None and not self._owner_live:
                raise self._fail(f"update {self._owner} handler issued {kind} after its recorded commands")
            return None
        index, event = cursor.events[cursor.next]
        if event.get("type") != kind:
            raise self._fail(f"command changed at history index {index}: history={event.get('type')} replay={kind}")
        return event

    def _fail(self, message: str) -> DeterminismError:
        error = DeterminismError(message)
        if self.determinism_error is None:
            self.determinism_error = error
        return error

    def is_timer_fired(self, timer_started: dict[str, Any]) -> bool:
        return any(event.get("type") == "TimerFired" and event.get("task_id") == timer_started.get("task_id") for event in self.history)

    def is_activity_canceled(self, activity_scheduled: dict[str, Any]) -> bool:
        return any(event.get("type") == "ActivityTaskCanceled" and event.get("task_id") == activity_scheduled.get("task_id") for event in self.history)

    def has_activity_retry_scheduled(self, activity_scheduled: dict[str, Any]) -> bool:
        return any(event.get("type") == "ActivityTaskRetryScheduled" and (event.get("attributes") or {}).get("previous_task") == activity_scheduled.get("task_id") for event in self.history)

    def activity_cancellation_reason(self, activity_scheduled: dict[str, Any]) -> str:
        event = next((candidate for candidate in self.history if candidate.get("type") == "ActivityTaskCanceled" and candidate.get("task_id") == activity_scheduled.get("task_id")), None)
        reason = (event.get("attributes") or {}).get("reason") if event else None
        return reason if isinstance(reason, str) and reason else "activity cancellation requested"

    def signal_args(self, name: str) -> list[list[Any]]:
        """Recorded arguments of every signal with this name, in history order."""
        return [
            (event.get("attributes") or {}).get("args") or []
            for event in self.signals
            if (event.get("attributes") or {}).get("signal_name") == name
        ]

    def completed_update_args(self, name: str) -> list[list[Any]]:
        """Recorded arguments of every completed update with this name, in history order."""
        return [
            (event.get("attributes") or {}).get("args") or []
            for event in self.completed_updates
            if (event.get("attributes") or {}).get("update_name") == name
        ]

    def is_cancellation_requested(self) -> bool:
        return self.cancellation is not None

    def cancellation_reason(self) -> str:
        reason = (self.cancellation.get("attributes") or {}).get("reason") if self.cancellation else None
        return reason if isinstance(reason, str) and reason else "workflow cancellation requested"
