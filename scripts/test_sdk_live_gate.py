"""The publishing gate against a scripted GitHub API (design D3 and D4)."""

from __future__ import annotations

import unittest

from sdk_live_gate import GateError, gate

SHA = "a" * 40
OTHER = "b" * 40
RUN = "https://github.com/postgrip-io/postgrip-sdk-live/actions/runs/{}"


class FakeGitHub:
    """Serves one status, runs and artifacts; each `sleep` advances one step."""

    def __init__(self, steps: list[dict]) -> None:
        self.steps = steps
        self.step = 0
        self.dispatches: list[dict] = []
        self.clock = 1_000_000.0

    @property
    def world(self) -> dict:
        return self.steps[min(self.step, len(self.steps) - 1)]

    def sleep(self, seconds: float) -> None:
        self.step += 1
        self.clock += seconds

    def now(self) -> float:
        return self.clock

    def api(self, method: str, path: str, token_env: str, body: dict | None) -> object:
        world = self.world
        if method == "POST":
            assert token_env == "SDK_LIVE_DISPATCH_TOKEN" and path.endswith("/live-pre-release.yml/dispatches")
            self.dispatches.append(body)
            return None
        if path.startswith("/repos/postgrip-io/postgrip-sdk/commits/"):
            assert token_env == "GITHUB_TOKEN"
            status = world.get("status")
            return {"statuses": [status] if status else []}
        assert token_env == "SDK_LIVE_DISPATCH_TOKEN"
        if "/workflows/live-pre-release.yml/runs" in path:
            return {"workflow_runs": world.get("runs", [])}
        run_id = path.split("/actions/runs/")[1].split("/")[0]
        run = world.get("run", {}).get(run_id)
        if path.endswith("/artifacts?per_page=100"):
            return {"artifacts": world.get("artifacts", {}).get(run_id, [])} if run else None
        return run


def status(state: str, run_id: int = 7) -> dict:
    return {"context": "postgrip-sdk-live/pre-release", "state": state, "target_url": RUN.format(run_id)}


def run(conclusion: str | None = "success", path: str = ".github/workflows/live-pre-release.yml") -> dict:
    return {"path": path, "status": "completed" if conclusion else "in_progress", "conclusion": conclusion}


def marker(sha: str) -> dict:
    return {"name": f"sdk-commit-{sha}"}


def accepted(run_id: int = 7, sha: str = SHA) -> dict:
    return {"status": status("success", run_id), "run": {str(run_id): run()}, "artifacts": {str(run_id): [marker(sha)]}}


def suite_run(state: str, sha: str = SHA) -> dict:
    return {"display_title": f"Pre-release SDK integration for {sha}", "status": state, "html_url": "run"}


def run_gate(github: FakeGitHub, minutes: float = 30) -> str:
    return gate(github.api, SHA, github.clock + minutes * 60, now=github.now, sleep=github.sleep)


class GateTests(unittest.TestCase):
    def test_an_accepted_run_passes_without_dispatching(self) -> None:
        github = FakeGitHub([accepted()])
        self.assertEqual(run_gate(github), RUN.format(7))
        self.assertEqual(github.dispatches, [])

    def test_no_status_dispatches_once_and_waits_for_the_accepted_run(self) -> None:
        github = FakeGitHub([{}, {"status": status("pending", 9), "runs": [suite_run("in_progress")]}, accepted(9)])
        self.assertEqual(run_gate(github), RUN.format(9))
        self.assertEqual(github.dispatches, [{"ref": "main", "inputs": {"sdk-sha": SHA}}])

    def test_an_in_progress_run_is_awaited_without_a_second_dispatch(self) -> None:
        github = FakeGitHub([{"status": status("pending")}, {"status": status("pending")}, accepted()])
        self.assertEqual(run_gate(github), RUN.format(7))
        self.assertEqual(github.dispatches, [])

    def test_a_failed_status_dispatches_again(self) -> None:
        github = FakeGitHub([{"status": status("failure", 3)}, accepted(4)])
        self.assertEqual(run_gate(github), RUN.format(4))
        self.assertEqual(len(github.dispatches), 1)

    def test_a_success_status_is_not_enough(self) -> None:
        # Design D3: a status anyone with write access could set is accepted only
        # through its run: wrong workflow, failed run, deleted run, wrong or extra marker.
        for world in [
            {"status": status("success"), "run": {"7": run(path=".github/workflows/live-nightly.yml")}, "artifacts": {"7": [marker(SHA)]}},
            {"status": status("success"), "run": {"7": run("failure")}, "artifacts": {"7": [marker(SHA)]}},
            {"status": status("success")},
            {"status": status("success"), "run": {"7": run()}, "artifacts": {"7": [marker(OTHER)]}},
            {"status": status("success"), "run": {"7": run()}, "artifacts": {"7": [marker(SHA), marker(OTHER)]}},
            {"status": {**status("success"), "target_url": "https://github.com/someone/else/actions/runs/7"}},
        ]:
            with self.subTest(world=world):
                github = FakeGitHub([world, accepted(8)])
                self.assertEqual(run_gate(github), RUN.format(8))
                self.assertEqual(len(github.dispatches), 1)

    def test_fails_once_every_dispatched_run_finished_without_acceptance(self) -> None:
        github = FakeGitHub([{}, {"status": status("pending", 5), "runs": [suite_run("in_progress")]},
                             {"status": status("failure", 5), "runs": [suite_run("completed")]}])
        with self.assertRaisesRegex(GateError, "finished without an accepted run"):
            run_gate(github)

    def test_a_run_that_failed_before_reporting_fails_the_gate(self) -> None:
        # The dispatched run ended before setting `pending`; the old failure remains.
        github = FakeGitHub([{"status": status("failure", 3)}, {"status": status("failure", 3), "runs": [suite_run("completed")]}])
        with self.assertRaisesRegex(GateError, "finished without an accepted run"):
            run_gate(github)

    def test_runs_for_other_commits_are_ignored(self) -> None:
        github = FakeGitHub([{}, {"runs": [suite_run("completed", OTHER)]}, accepted()])
        self.assertEqual(run_gate(github), RUN.format(7))

    def test_an_awaited_run_that_fails_fails_the_gate(self) -> None:
        github = FakeGitHub([{"status": status("pending")}, {"status": status("failure")}])
        with self.assertRaisesRegex(GateError, "ended failure"):
            run_gate(github)

    def test_gives_up_at_the_deadline(self) -> None:
        github = FakeGitHub([{"status": status("pending")}])
        with self.assertRaisesRegex(GateError, "before the deadline"):
            run_gate(github, minutes=3)

    def test_rejects_a_malformed_commit(self) -> None:
        with self.assertRaisesRegex(GateError, "40-character"):
            gate(FakeGitHub([{}]).api, "main", 0)


if __name__ == "__main__":
    unittest.main()
