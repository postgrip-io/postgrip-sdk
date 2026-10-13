"""Multi-page history walking over the Agent's task-event and workflow-history
page operations. The walker validates cursors; the page source performs I/O."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, Protocol

from .types import TaskEvent, TaskEventPage, WorkflowHistoryEvent, WorkflowHistoryPage

_HISTORY_PAGE_MAXIMUM_LIMIT = 500


class TaskEventPages(Protocol):
    def get_task_events_page(self, task_id: str, *, cursor: str | None = None, limit: int | None = None) -> TaskEventPage: ...


class WorkflowHistoryPages(Protocol):
    def get_workflow_history_page(
        self, workflow_id_or_run_id: str, *, cursor: str | None = None, limit: int | None = None
    ) -> WorkflowHistoryPage: ...


def _iter_history_pages(
    fetch_page: Callable[[str | None], Mapping[str, Any]],
) -> Iterator[Any]:
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        page = fetch_page(cursor)
        items = page.get("items")
        if not isinstance(items, list):
            raise RuntimeError("postgrip-agent: history page is missing its items array")
        yield from items
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            return
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            raise RuntimeError("postgrip-agent: history page returned an empty next cursor")
        cursor = next_cursor.strip()
        if cursor in seen:
            raise RuntimeError("postgrip-agent: history page repeated its next cursor")
        seen.add(cursor)


def iter_task_events(source: TaskEventPages, task_id: str) -> Iterator[TaskEvent]:
    return _iter_history_pages(
        lambda cursor: source.get_task_events_page(
            task_id,
            cursor=cursor,
            limit=_HISTORY_PAGE_MAXIMUM_LIMIT,
        )
    )


def iter_workflow_history(source: WorkflowHistoryPages, workflow_id_or_run_id: str) -> Iterator[WorkflowHistoryEvent]:
    return _iter_history_pages(
        lambda cursor: source.get_workflow_history_page(
            workflow_id_or_run_id,
            cursor=cursor,
            limit=_HISTORY_PAGE_MAXIMUM_LIMIT,
        )
    )
