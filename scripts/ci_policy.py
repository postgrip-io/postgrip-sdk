#!/usr/bin/env python3
"""Select Markdown-only PR validation and verify the aggregate CI result."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


RUNTIME_JOBS = ("contracts", "go", "typescript", "python", "recorded-endpoints", "artifacts")


def select_docs_only(
    event_name: str, event: dict, *, force_full: bool = False, repository: str = "."
) -> tuple[bool, str]:
    if force_full or event_name != "pull_request":
        return False, "Full validation required for this invocation."

    def git(*args: str) -> bytes:
        return subprocess.check_output(
            ["git", *args], cwd=repository, stderr=subprocess.PIPE
        )

    try:
        pr = event["pull_request"]
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha)
                   for sha in (base, head)):
            raise ValueError("Invalid commit identifiers")
        parents = git("rev-list", "--parents", "-n", "1", "HEAD").decode().split()
        if len(parents) != 3 or parents[1:] != [base, head]:
            return False, "Tested merge parents do not match the PR event; running full validation."
        changed = git(
            "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z",
            base, parents[0], "--",
        )
        if not changed or not changed.endswith(b"\0"):
            return False, "No complete nonempty diff available; running full validation."
        paths = changed[:-1].split(b"\0")
        if not all(path.endswith(b".md") for path in paths):
            return False, "The PR includes non-Markdown changes; running full validation."
        return True, f"All {len(paths)} changed paths end in .md; running documentation validation."
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError):
        return False, "Unable to establish a Markdown-only diff; running full validation."


def validate_results(needs: dict) -> list[str]:
    """Accept only successful selected jobs and explicitly permitted skips."""
    failures = []
    expected = {"changes", "documentation", *RUNTIME_JOBS}
    if set(needs) != expected:
        failures.append("Aggregate gate dependencies do not match the CI job inventory.")
    selection = needs.get("changes", {})
    docs_only = selection.get("outputs", {}).get("docs_only")
    if docs_only not in ("true", "false"):
        failures.append("Missing or invalid documentation-only selection output.")
    for name in sorted(expected):
        result = needs.get(name, {}).get("result")
        allowed = {"success"}
        if name in RUNTIME_JOBS and docs_only == "true":
            allowed.add("skipped")
        if result not in allowed:
            failures.append(f"{name}: expected {' or '.join(sorted(allowed))}, got {result!r}.")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-result", action="store_true")
    args = parser.parse_args()
    if args.check_result:
        try:
            needs = json.loads(os.environ["CI_NEEDS_JSON"])
            failures = validate_results(needs)
        except (KeyError, TypeError, ValueError, AttributeError):
            failures = ["Missing or malformed aggregate CI results."]
        for failure in failures:
            print(failure, file=sys.stderr)
        if not failures:
            print("All selected SDK validation jobs succeeded.")
        return int(bool(failures))

    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    except (KeyError, OSError, ValueError):
        event = {}
    docs_only, reason = select_docs_only(
        os.environ.get("GITHUB_EVENT_NAME", ""), event,
        force_full=os.environ.get("CI_FORCE_FULL", "false") != "false",
    )
    print(reason)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"docs_only={str(docs_only).lower()}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"{reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
