#!/usr/bin/env python3
"""Publishing gate: wait for an accepted stage pre-release run of this commit.

Design: docs/design/live-suites-private-repository-20261109.md, D3 and D4.
The stage suites run in the private postgrip-io/postgrip-sdk-live, which sets
the `postgrip-sdk-live/pre-release` status on the SDK commit it tested. This
gate:

1. passes if that status links a run accepted for the commit (D3);
2. otherwise, unless a run is already in progress, dispatches
   `live-pre-release.yml` with `sdk-sha` set to the commit;
3. waits for an accepted run, and fails once every run for the commit that
   started after the dispatch has finished without one, or at the deadline.

Tokens come from the environment only:
- GITHUB_TOKEN reads this public repository's commit statuses;
- SDK_LIVE_DISPATCH_TOKEN (Actions: write on postgrip-sdk-live) reads its runs
  and artifacts and dispatches the suite.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

SDK = "postgrip-io/postgrip-sdk"
LIVE = "postgrip-io/postgrip-sdk-live"
CONTEXT = "postgrip-sdk-live/pre-release"
WORKFLOW = "live-pre-release.yml"
RUN_URL = re.compile(r"https://github\.com/postgrip-io/postgrip-sdk-live/actions/runs/(\d+)")
MARKER = re.compile(r"sdk-commit-([0-9a-f]{40})")
SHA = re.compile(r"[0-9a-f]{40}")


class GateError(Exception):
    pass


Api = Callable[[str, str, str, "dict | None"], object]


def github_api(method: str, path: str, token_env: str, body: dict | None = None) -> object:
    token = os.environ.get(token_env, "")
    if not token:
        raise GateError(f"{token_env} is not set")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "postgrip-sdk-live-gate", "Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"https://api.github.com{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        if error.code == 404 and method == "GET":
            return None
        raise GateError(f"{method} {path}: HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise GateError(f"{method} {path}: {error.reason}") from None


@dataclass
class Evidence:
    """What the commit's status says, and whether its run is accepted (D3)."""

    state: str  # "absent", "pending", "success", "failure" or "error"
    accepted: bool
    run_url: str = ""
    updated_at: str = ""


def evidence(api: Api, sha: str) -> Evidence:
    combined = api("GET", f"/repos/{SDK}/commits/{sha}/status?per_page=100", "GITHUB_TOKEN", None) or {}
    status = next((s for s in combined.get("statuses", []) if s.get("context") == CONTEXT), None)
    if status is None:
        return Evidence("absent", False)
    url = status.get("target_url") or ""
    found = Evidence(status.get("state", "error"), False, url, status.get("updated_at", ""))
    match = RUN_URL.fullmatch(url)
    if found.state != "success" or not match:
        return found
    run_path = f"/repos/{LIVE}/actions/runs/{match.group(1)}"
    run = api("GET", run_path, "SDK_LIVE_DISPATCH_TOKEN", None)
    if not run or run.get("path") != f".github/workflows/{WORKFLOW}" or run.get("status") != "completed" \
            or run.get("conclusion") != "success":
        return found
    artifacts = (api("GET", f"{run_path}/artifacts?per_page=100", "SDK_LIVE_DISPATCH_TOKEN", None) or {}).get("artifacts", [])
    markers = [m.group(1) for a in artifacts if not a.get("expired") and (m := MARKER.fullmatch(a.get("name", "")))]
    found.accepted = markers == [sha]
    return found


def runs_since(api: Api, sha: str, since: str) -> list[dict]:
    """This commit's suite runs created at or after `since` (run-name names the commit)."""
    path = f"/repos/{LIVE}/actions/workflows/{WORKFLOW}/runs?event=workflow_dispatch&created=%3E%3D{since}&per_page=100"
    runs = (api("GET", path, "SDK_LIVE_DISPATCH_TOKEN", None) or {}).get("workflow_runs", [])
    return [run for run in runs if (run.get("display_title") or "").endswith(sha)]


def dispatch(api: Api, sha: str) -> None:
    api("POST", f"/repos/{LIVE}/actions/workflows/{WORKFLOW}/dispatches", "SDK_LIVE_DISPATCH_TOKEN",
        {"ref": "main", "inputs": {"sdk-sha": sha}})


def gate(api: Api, sha: str, deadline: float, now: Callable[[], float] = time.time,
         sleep: Callable[[float], None] = time.sleep, interval: float = 60) -> str:
    """Returns the accepted run's URL, or raises GateError."""
    if not SHA.fullmatch(sha):
        raise GateError("the SDK commit must be a full 40-character lowercase SHA")
    first = evidence(api, sha)
    if first.accepted:
        return first.run_url
    since = None
    if first.state != "pending":
        since = dt.datetime.fromtimestamp(now(), dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        dispatch(api, sha)
        print(f"No accepted pre-release run for {sha[:12]} ({first.state}); dispatched {WORKFLOW}.", flush=True)
    else:
        print(f"A pre-release run for {sha[:12]} is in progress: {first.run_url}", flush=True)
    while True:
        sleep(interval)
        current = evidence(api, sha)
        if current.accepted:
            return current.run_url
        if since is not None:
            runs = runs_since(api, sha, since)
            if runs and all(run.get("status") == "completed" for run in runs) and current.state != "pending":
                raise GateError(f"the pre-release suite finished without an accepted run for {sha}: "
                                + ", ".join(run.get("html_url", "") for run in runs))
        elif current.state not in ("pending", "success"):
            raise GateError(f"the in-progress pre-release run ended {current.state}: {current.run_url}")
        if now() >= deadline:
            raise GateError(f"no accepted pre-release run for {sha} before the deadline; re-run this job to keep waiting")


def main(argv: list[str]) -> int:
    sha = argv[0] if argv else os.environ.get("GITHUB_SHA", "")
    minutes = float(os.environ.get("SDK_LIVE_GATE_MINUTES", "340"))
    try:
        url = gate(github_api, sha, time.time() + minutes * 60)
    except GateError as error:
        print(f"sdk_live_gate: {error}", file=sys.stderr)
        return 1
    print(f"Accepted pre-release run for {sha[:12]}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
