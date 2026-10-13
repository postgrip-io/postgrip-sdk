"""Durable-history replay for the Agent workflow runtime.

Replay walks the history a workflow task fetched and serves recorded commands
back to the workflow body. It owns ``DeterminismError`` and depends on no SDK
failure type; the Agent translates the error at its runtime boundary.
"""

from __future__ import annotations

from typing import Any


class DeterminismError(Exception):
    """Workflow code disagreed with durable history."""


class WorkflowReplay:
    def __init__(self, history: list[dict[str, Any]]):
        self.history = history
        self.activities = [event for event in history if event.get("type") == "ActivityTaskScheduled"]
        self.timers = [event for event in history if event.get("type") == "TimerStarted"]
        self.signals = [event for event in history if event.get("type") == "WorkflowSignaled"]
        self.children = [event for event in history if event.get("type") == "ChildWorkflowExecutionStarted"]
        self.completed_updates = [event for event in history if event.get("type") == "WorkflowUpdateCompleted"]
        self.cancellation = next((event for event in history if event.get("type") == "WorkflowCancellationRequested"), None)
        self.activity_index = 0
        self.timer_index = 0
        self.child_index = 0

    def next_activity(self, activity_type: str) -> dict[str, Any] | None:
        event = self.activities[self.activity_index] if self.activity_index < len(self.activities) else None
        self.activity_index += 1
        if event and (event.get("attributes") or {}).get("activity_type") != activity_type:
            raise DeterminismError(f"activity command changed at index {self.activity_index}: history={(event.get('attributes') or {}).get('activity_type')} replay={activity_type}")
        return event

    def next_timer(self, duration_ms: int | None = None) -> dict[str, Any] | None:
        event = self.timers[self.timer_index] if self.timer_index < len(self.timers) else None
        self.timer_index += 1
        history_duration = (event.get("attributes") or {}).get("duration_ms") if event else None
        if event and duration_ms is not None and history_duration is not None and round(duration_ms) != history_duration:
            raise DeterminismError(f"timer command changed at index {self.timer_index}: history={history_duration} replay={round(duration_ms)}")
        return event

    def next_child(self, workflow_type: str) -> dict[str, Any] | None:
        event = self.children[self.child_index] if self.child_index < len(self.children) else None
        self.child_index += 1
        if event and (event.get("attributes") or {}).get("workflow_type") != workflow_type:
            raise DeterminismError(f"child workflow command changed at index {self.child_index}: history={(event.get('attributes') or {}).get('workflow_type')} replay={workflow_type}")
        return event

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
