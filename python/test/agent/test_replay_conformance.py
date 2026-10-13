from __future__ import annotations

import json
import unittest
from pathlib import Path

from postgrip.agent._replay import DeterminismError, WorkflowReplay

FIXTURES = Path(__file__).resolve().parents[3] / "test" / "fixtures" / "replay"


class SharedReplayConformanceTests(unittest.TestCase):
    """The shared fixtures in test/fixtures/replay run unchanged in every SDK language."""

    def test_fixtures(self) -> None:
        files = sorted(FIXTURES.glob("*.json"))
        self.assertTrue(files, f"no replay fixtures in {FIXTURES}")
        for path in files:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text(encoding="utf-8"))
                replay = WorkflowReplay(fixture["history"])
                for index, step in enumerate(fixture["steps"]):
                    try:
                        if step["command"] == "activity":
                            event = replay.next_activity(step["name"])
                        elif step["command"] == "timer":
                            event = replay.next_timer(step["duration_ms"])
                        else:
                            event = replay.next_child(step["workflow_type"])
                        outcome = "replay" if event else "new"
                    except DeterminismError:
                        outcome = "nondeterministic"
                    self.assertEqual((index, outcome), (index, step["expect"]))
                expects_violation = any(step["expect"] == "nondeterministic" for step in fixture["steps"])
                self.assertEqual(replay.determinism_error is not None, expects_violation)


if __name__ == "__main__":
    unittest.main()
