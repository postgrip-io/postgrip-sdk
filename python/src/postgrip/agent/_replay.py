"""Durable-history replay for the Agent workflow runtime.

Replay walks the history a workflow task fetched and serves recorded commands
back to the workflow body. It owns ``DeterminismError`` and depends on no SDK
failure type; the Agent translates the error at its runtime boundary.
"""

from __future__ import annotations

from typing import Any


class DeterminismError(Exception):
    """Workflow code disagreed with durable history."""


_COMMAND_TYPES = frozenset({"ActivityTaskScheduled", "TimerStarted", "ChildWorkflowExecutionStarted"})


class WorkflowReplay:
    def __init__(self, history: list[dict[str, Any]]):
        self.history = history
        # Command events in history order; workflow code must consume them in this order.
        self.commands = [(index, event) for index, event in enumerate(history) if event.get("type") in _COMMAND_TYPES]
        self.signals = [event for event in history if event.get("type") == "WorkflowSignaled"]
        self.completed_updates = [event for event in history if event.get("type") == "WorkflowUpdateCompleted"]
        self.cancellation = next((event for event in history if event.get("type") == "WorkflowCancellationRequested"), None)
        self.command_cursor = 0
        self.activity_index = 0
        self.timer_index = 0
        self.child_index = 0
        # The first determinism error raised; a caught one still fails the task.
        self.determinism_error: DeterminismError | None = None

    def next_activity(self, activity_type: str) -> dict[str, Any] | None:
        event = self._next_command("ActivityTaskScheduled")
        if event and (event.get("attributes") or {}).get("activity_type") != activity_type:
            raise self._fail(f"activity command changed at index {self.activity_index + 1}: history={(event.get('attributes') or {}).get('activity_type')} replay={activity_type}")
        if event:
            self.activity_index += 1
            self.command_cursor += 1
        return event

    def next_timer(self, duration_ms: int | None = None) -> dict[str, Any] | None:
        event = self._next_command("TimerStarted")
        history_duration = (event.get("attributes") or {}).get("duration_ms") if event else None
        if event and duration_ms is not None and history_duration is not None and round(duration_ms) != history_duration:
            raise self._fail(f"timer command changed at index {self.timer_index + 1}: history={history_duration} replay={round(duration_ms)}")
        if event:
            self.timer_index += 1
            self.command_cursor += 1
        return event

    def next_child(self, workflow_type: str) -> dict[str, Any] | None:
        event = self._next_command("ChildWorkflowExecutionStarted")
        if event and (event.get("attributes") or {}).get("workflow_type") != workflow_type:
            raise self._fail(f"child workflow command changed at index {self.child_index + 1}: history={(event.get('attributes') or {}).get('workflow_type')} replay={workflow_type}")
        if event:
            self.child_index += 1
            self.command_cursor += 1
        return event

    def _next_command(self, kind: str) -> dict[str, Any] | None:
        """The earliest unconsumed command event, without consuming it.

        ``None`` when none remains (the command is new). A different kind is a
        determinism error, covering reordering and a kind whose events ran out
        while others remain.
        """
        if self.command_cursor >= len(self.commands):
            return None
        index, event = self.commands[self.command_cursor]
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
