from __future__ import annotations

from typing import Any


def milestone_event(
    name: str,
    *,
    index: int | None,
    total: int | None,
    status: str,
    details: dict[str, Any] | None,
) -> dict[str, Any]:
    event_details = {
        **(details or {}),
        "milestone": True,
        "name": name,
        "status": status,
    }
    if index is not None:
        event_details["index"] = index
    if total is not None:
        event_details["total"] = total
    prefix = f"step {index}/{total} " if index is not None and total is not None else ""
    return {
        "kind": "milestone",
        "stage": "milestone",
        "message": f"{prefix}{status} {name}".strip(),
        "details": event_details,
    }
