"""Exercise CI selection using real Git trees, plus aggregate result failures."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from ci_policy import RUNTIME_JOBS, select_docs_only, validate_results


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q", "-b", "main")
        (self.root / "README.md").write_text("original documentation\n")
        (self.root / "code.py").write_text("print('original')\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "topic")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "user.name=CI fixture", "-c", "user.email=ci@example.invalid", *args],
            cwd=self.root, stderr=subprocess.PIPE,
        ).decode().strip()

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture", "--allow-empty")

    def merge(self, *, advance_base: bool = False) -> dict:
        self.commit()
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        if advance_base:
            (self.root / "base-only.py").write_text("print('base changed')\n")
            self.commit()
            self.base = self.git("rev-parse", "HEAD")
        self.git("merge", "-q", "--no-ff", "topic", "-m", "test merge")
        return {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}

    def selection(self, event: dict, **options) -> bool:
        return select_docs_only("pull_request", event, repository=str(self.root), **options)[0]

    def test_markdown_add_edit_delete_and_unusual_names(self) -> None:
        (self.root / "README.md").unlink()
        (self.root / "notes with spaces\nand newline.md").write_text("new docs\n")
        self.assertTrue(self.selection(self.merge()))

    def test_markdown_edit(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        self.assertTrue(self.selection(self.merge()))

    def test_mixed_changes(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        (self.root / "code.py").write_text("print('changed')\n")
        self.assertFalse(self.selection(self.merge()))

    def test_non_markdown_deletion(self) -> None:
        (self.root / "code.py").unlink()
        self.assertFalse(self.selection(self.merge()))

    def test_code_renamed_to_markdown(self) -> None:
        (self.root / "code.py").rename(self.root / "code.md")
        self.assertFalse(self.selection(self.merge()))

    def test_markdown_renamed_to_code(self) -> None:
        (self.root / "README.md").rename(self.root / "notes.py")
        self.assertFalse(self.selection(self.merge()))

    def test_markdown_rename(self) -> None:
        (self.root / "README.md").rename(self.root / "notes.md")
        self.assertTrue(self.selection(self.merge()))

    def test_uppercase_suffix_runs_full(self) -> None:
        (self.root / "guide.MD").write_text("content\n")
        self.assertFalse(self.selection(self.merge()))

    def test_workflow_configuration_runs_full(self) -> None:
        (self.root / "mkdocs.yml").write_text("site_name: fixture\n")
        self.assertFalse(self.selection(self.merge()))

    def test_mdx_runs_full(self) -> None:
        (self.root / "guide.mdx").write_text("content\n")
        self.assertFalse(self.selection(self.merge()))

    def test_base_only_code_change_is_not_a_pr_change(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        self.assertTrue(self.selection(self.merge(advance_base=True)))

    def test_empty_diff_runs_full(self) -> None:
        self.assertFalse(self.selection(self.merge()))

    def test_untrusted_or_missing_comparison_runs_full(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        valid = self.merge()
        for event in ({}, None, {"pull_request": []},
                      {"pull_request": {"base": {"sha": "--help"}, "head": {"sha": self.base}}},
                      {"pull_request": {"base": {"sha": "0" * 40}, "head": valid["pull_request"]["head"]}}):
            with self.subTest(event=event):
                self.assertFalse(self.selection(event))
        self.git("checkout", "-q", "topic")
        self.assertFalse(self.selection(valid))

    def test_depth_two_checkout_is_sufficient(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        event = self.merge(advance_base=True)
        with tempfile.TemporaryDirectory() as shallow:
            subprocess.run(["git", "clone", "-q", "--depth=2", self.root.as_uri(), shallow], check=True)
            self.assertTrue(select_docs_only("pull_request", event, repository=shallow)[0])

    def test_missing_git_objects_run_full(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        event = self.merge()
        with tempfile.TemporaryDirectory() as shallow:
            subprocess.run(["git", "clone", "-q", "--depth=1", self.root.as_uri(), shallow], check=True)
            self.assertFalse(select_docs_only("pull_request", event, repository=shallow)[0])

    def test_pushes_and_reusable_calls_run_full(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        event = self.merge()
        for kind in ("push", "workflow_call", "workflow_dispatch", ""):
            self.assertFalse(select_docs_only(kind, event, repository=str(self.root))[0])
        self.assertFalse(self.selection(event, force_full=True))

    def test_cli_writes_selection_output(self) -> None:
        (self.root / "README.md").write_text("edited docs\n")
        event = self.merge()
        event_file = self.root / "event.json"
        event_file.write_text(json.dumps(event))
        output = self.root / "output"
        summary = self.root / "summary"
        environment = {**os.environ, "GITHUB_EVENT_NAME": "pull_request",
                       "GITHUB_EVENT_PATH": str(event_file), "GITHUB_OUTPUT": str(output),
                       "GITHUB_STEP_SUMMARY": str(summary), "CI_FORCE_FULL": "false"}
        result = subprocess.run(
            [os.sys.executable, str(Path(__file__).with_name("ci_policy.py"))],
            cwd=self.root, env=environment, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), "docs_only=true\n")
        self.assertIn("documentation validation", summary.read_text())


class GateTests(unittest.TestCase):
    def results(self, docs_only: bool) -> dict:
        needs = {name: {"result": "skipped" if docs_only else "success"} for name in RUNTIME_JOBS}
        needs["changes"] = {"result": "success", "outputs": {"docs_only": str(docs_only).lower()}}
        needs["documentation"] = {"result": "success"}
        return needs

    def test_successful_full_and_documentation_runs(self) -> None:
        self.assertEqual(validate_results(self.results(False)), [])
        self.assertEqual(validate_results(self.results(True)), [])

    def test_failure_cancellation_and_required_skips(self) -> None:
        for docs_only in (False, True):
            for name in self.results(docs_only):
                statuses = ["failure", "cancelled"]
                if not docs_only or name not in RUNTIME_JOBS:
                    statuses.append("skipped")
                for status in statuses:
                    with self.subTest(docs_only=docs_only, name=name, status=status):
                        needs = self.results(docs_only)
                        needs[name]["result"] = status
                        self.assertTrue(validate_results(needs))

    def test_missing_or_invalid_selection(self) -> None:
        for output in ({}, {"docs_only": ""}, {"docs_only": "yes"}):
            needs = self.results(True)
            needs["changes"]["outputs"] = output
            self.assertTrue(validate_results(needs))

    def test_gate_inventory_cannot_silently_drop_jobs(self) -> None:
        needs = self.results(False)
        del needs["go"]
        self.assertTrue(validate_results(needs))
        needs = self.results(False)
        needs["new-job"] = {"result": "success"}
        self.assertTrue(validate_results(needs))


if __name__ == "__main__":
    unittest.main()
