"""Pure Agent client transformations: workflow memo and UI metadata, option
normalization and result-wait decisions. Nothing here performs I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import TaskFailedError
from .types import Task, WorkflowExecution

_POSTGRIP_UI_MEMO_KEY = "postgrip.ui"


@dataclass(frozen=True)
class _WorkflowResultStep:
    """What a workflow result wait does after reading one task snapshot."""

    done: bool = False
    value: Any = None
    next_task_id: str | None = None
    resolve: bool = False


def _workflow_result_step(
    task: Task,
    task_id: str,
    workflow: WorkflowExecution | None = None,
) -> _WorkflowResultStep:
    """Decide the next result-wait step; an empty step means keep waiting.

    A failed task needs the workflow's current run: pass *workflow* once the
    caller has read it after a ``resolve`` step.
    """
    if task["state"] == "succeeded":
        result = task.get("result") or {}
        next_task_id = (result.get("continue_as_new") or {}).get("task_id")
        if next_task_id:
            return _WorkflowResultStep(next_task_id=next_task_id)
        return _WorkflowResultStep(done=True, value=result.get("value"))
    if task["state"] == "failed":
        if workflow is None:
            return _WorkflowResultStep(resolve=True)
        if workflow["state"] == "running" and workflow["task_id"] != task_id:
            return _WorkflowResultStep(next_task_id=workflow["task_id"])
        raise TaskFailedError(task["id"], task.get("error") or "workflow failed")
    return _WorkflowResultStep()


def _workflow_query_options(options: Mapping[str, Any]) -> dict[str, Any]:
    mapping = {
        "workflow_id": "id",
        "run_id": "run_id",
        "workflow_type": "type",
        "task_queue": "queue",
        "order_by": "order_by",
        "page_token": "page_token",
        "search_attributes": "search_attributes",
    }
    return {mapping.get(key, key): value for key, value in options.items() if value is not None}


def _memo_with_workflow_ui(memo: Mapping[str, Any] | None, ui: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not ui:
        return memo
    ui_memo = _workflow_ui_memo(ui)
    if not ui_memo:
        return memo
    return {**(memo or {}), _POSTGRIP_UI_MEMO_KEY: ui_memo}


def _workflow_ui_memo(ui: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    display_name = _clean_string(ui.get("displayName") or ui.get("display_name"))
    if display_name:
        out["displayName"] = display_name
    description = _clean_string(ui.get("description"))
    if description:
        out["description"] = description
    details = ui.get("details")
    if isinstance(details, dict):
        clean_details = {str(key).strip(): value for key, value in details.items() if str(key).strip()}
        if clean_details:
            out["details"] = clean_details
    tags = ui.get("tags")
    if isinstance(tags, list):
        clean_tags = [_clean_string(tag) for tag in tags]
        clean_tags = [tag for tag in clean_tags if tag]
        if clean_tags:
            out["tags"] = clean_tags
    return out


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _normalize_temporal_start_options(options: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(options)
    if "id" in normalized and "workflow_id" not in normalized:
        normalized["workflow_id"] = normalized.pop("id")
    return normalized


def _definition_name(value: Any) -> str:
    return value if isinstance(value, str) else value.name


def _duration_ms(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds() * 1000)
    return int(value)
