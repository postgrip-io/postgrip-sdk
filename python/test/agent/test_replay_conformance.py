from __future__ import annotations

import json
import unittest
from pathlib import Path

from postgrip.agent._replay import DeterminismError, WorkflowReplay, ownership_candidates

FIXTURES = Path(__file__).resolve().parents[3] / "test" / "fixtures" / "replay"


class SharedReplayConformanceTests(unittest.TestCase):
    """The shared fixtures in test/fixtures/replay run unchanged in every SDK language."""

    def test_fixtures(self) -> None:
        files = sorted(FIXTURES.glob("*.json"))
        self.assertTrue(files, f"no replay fixtures in {FIXTURES}")
        for path in files:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text(encoding="utf-8"))
                replay = WorkflowReplay(fixture["history"], fixture.get("owners"))
                for index, step in enumerate(fixture["steps"]):
                    owner = step.get("owner")
                    restore = replay.enter_owner(owner, step.get("live", False)) if owner else (lambda: None)
                    try:
                        if step["command"] == "complete":
                            replay.check_body_consumed()
                            outcome = "ok"
                        elif step["command"] == "handler_done":
                            replay.check_owner_consumed(owner)
                            outcome = "ok"
                        else:
                            if step["command"] == "activity":
                                event = replay.next_activity(step["name"])
                            elif step["command"] == "timer":
                                event = replay.next_timer(step["duration_ms"])
                            else:
                                event = replay.next_child(step["workflow_type"])
                            outcome = "replay" if event else "new"
                    except DeterminismError:
                        outcome = "nondeterministic"
                    finally:
                        restore()
                    self.assertEqual((index, outcome), (index, step["expect"]))
                expects_violation = any(step["expect"] == "nondeterministic" for step in fixture["steps"])
                self.assertEqual(replay.determinism_error is not None, expects_violation)


class OwnershipCandidatesTests(unittest.TestCase):
    def test_only_commands_inside_an_update_window(self) -> None:
        def event(type_: str, task_id: str) -> dict:
            return {"type": type_, "task_id": task_id}

        self.assertEqual(
            ownership_candidates([
                event("ActivityTaskScheduled", "before-any-update"),
                event("WorkflowUpdateAccepted", "update-1"),
                event("TimerStarted", "inside-update-1"),
                event("WorkflowUpdateCompleted", "update-1"),
                event("ChildWorkflowExecutionStarted", "between-updates"),
                event("WorkflowUpdateAccepted", "update-2"),
                event("ActivityTaskScheduled", "while-update-2-pending"),
            ]),
            ["inside-update-1", "while-update-2-pending"],
        )
        self.assertEqual(
            ownership_candidates([
                event("ActivityTaskScheduled", "before-legacy"),
                event("WorkflowUpdateCompleted", "legacy-1"),
                event("ActivityTaskScheduled", "after-legacy"),
            ]),
            ["before-legacy"],
        )


if __name__ == "__main__":
    unittest.main()
