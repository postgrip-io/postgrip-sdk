#!/usr/bin/env python3
"""Exercise disposable GitHub App adoption and automatic deployment.

This suite is intentionally separate from the exhaustive operation inventory:
it owns the external GitHub lifecycle that a recorded HTTP fixture cannot
prove. It creates exactly one private repository in a dedicated test
organization, adopts it into a dedicated PostGrip project, optionally waits
until the originally issued installation token would be expired, creates one
GitHub commit, observes the resulting deployment, and always deletes the
repository. On stage, given a Worker instead of a project, it creates that
project on the disposable repository itself and leaves it to the stage reset.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

SAFE_REPOSITORY_PREFIX = "postgrip-live-"
TERMINAL_OPERATION_STATES = frozenset({"succeeded", "failed", "blocked"})
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class LiveAdoptionError(RuntimeError):
    """A redacted, operator-actionable live-suite failure."""


@dataclass(frozen=True)
class Settings:
    service_url: str
    postgrip_token: str
    project_id: str
    worker_id: str
    github_api_url: str
    github_token: str
    github_org: str
    wait_for_expiry: bool
    expiry_wait_seconds: int


def required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise LiveAdoptionError(f"{name} is required")
    return value


def load_settings(environ: Mapping[str, str]) -> Settings:
    if environ.get("POSTGRIP_GITHUB_LIVE_DISPOSABLE", "").strip().lower() != "true":
        raise LiveAdoptionError("POSTGRIP_GITHUB_LIVE_DISPOSABLE=true is required")
    service_url = environ.get("POSTGRIP_SERVICE_URL", "").strip() or required(
        environ, "POSTGRIP_URL"
    )
    github_api_url = environ.get(
        "POSTGRIP_GITHUB_TEST_API_URL", "https://api.github.com"
    ).strip()
    for name, value in (("PostGrip Service", service_url), ("GitHub API", github_api_url)):
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise LiveAdoptionError(f"{name} URL must be an HTTPS origin without credentials")
    project_id = environ.get("POSTGRIP_GITHUB_LIVE_PROJECT_ID", "").strip()
    worker_id = environ.get("POSTGRIP_GITHUB_LIVE_WORKER_ID", "").strip()
    if bool(project_id) == bool(worker_id):
        raise LiveAdoptionError(
            "set exactly one of POSTGRIP_GITHUB_LIVE_PROJECT_ID or POSTGRIP_GITHUB_LIVE_WORKER_ID"
        )
    for name, value in (
        ("POSTGRIP_GITHUB_LIVE_PROJECT_ID", project_id),
        ("POSTGRIP_GITHUB_LIVE_WORKER_ID", worker_id),
    ):
        if value and UUID_PATTERN.fullmatch(value) is None:
            raise LiveAdoptionError(f"{name} must be a UUID")
    # A run-owned project is never deleted here; only a stage reset removes it.
    if worker_id:
        required(environ, "POSTGRIP_LIVE_STAGE_LEASE")
    org = required(environ, "POSTGRIP_GITHUB_TEST_ORG")
    if org.lower() in {"postgrip", "postgrip-io"}:
        raise LiveAdoptionError("the production PostGrip GitHub organization is forbidden")
    wait_for_expiry = (
        environ.get("POSTGRIP_GITHUB_LIVE_WAIT_FOR_EXPIRY", "false").strip().lower()
        == "true"
    )
    try:
        expiry_wait_seconds = int(
            environ.get("POSTGRIP_GITHUB_LIVE_EXPIRY_WAIT_SECONDS", "3900")
        )
    except ValueError as exc:
        raise LiveAdoptionError(
            "POSTGRIP_GITHUB_LIVE_EXPIRY_WAIT_SECONDS must be an integer"
        ) from exc
    if wait_for_expiry and not 3600 <= expiry_wait_seconds <= 4500:
        raise LiveAdoptionError("expiry wait must be between 3600 and 4500 seconds")
    return Settings(
        service_url=service_url.rstrip("/"),
        postgrip_token=required(environ, "POSTGRIP_TOKEN"),
        project_id=project_id,
        worker_id=worker_id,
        github_api_url=github_api_url.rstrip("/"),
        github_token=required(environ, "POSTGRIP_GITHUB_TEST_TOKEN"),
        github_org=org,
        wait_for_expiry=wait_for_expiry,
        expiry_wait_seconds=expiry_wait_seconds,
    )


def request_json(
    method: str,
    url: str,
    *,
    token: str,
    body: Any = None,
    headers: Mapping[str, str] | None = None,
    expected: tuple[int, ...] = (200,),
) -> Any:
    payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "postgrip-github-adoption-live-suite",
    }
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url, data=payload, method=method, headers=request_headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise LiveAdoptionError("live API response exceeded 1 MiB")
            if response.status not in expected:
                raise LiveAdoptionError(
                    f"{method} {urllib.parse.urlparse(url).path} returned {response.status}"
                )
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        try:
            problem = json.loads(exc.read(16_385))
            code = problem.get("code") or problem.get("message") or "request failed"
        except (ValueError, AttributeError):
            code = "request failed"
        raise LiveAdoptionError(
            f"{method} {urllib.parse.urlparse(url).path} returned {exc.code}: {code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LiveAdoptionError(
            f"{method} {urllib.parse.urlparse(url).path} could not connect"
        ) from exc


def postgrip_request(
    settings: Settings,
    method: str,
    path: str,
    *,
    body: Any = None,
    etag: str = "",
    expected: tuple[int, ...] = (200,),
) -> Any:
    headers: dict[str, str] = {}
    if method not in {"GET", "HEAD"}:
        headers["Idempotency-Key"] = f"github-live-{uuid.uuid4()}"
    if etag:
        headers["If-Match"] = etag
    return request_json(
        method,
        settings.service_url + path,
        token=settings.postgrip_token,
        body=body,
        headers=headers,
        expected=expected,
    )


def github_request(
    settings: Settings,
    method: str,
    path: str,
    *,
    body: Any = None,
    expected: tuple[int, ...] = (200,),
) -> Any:
    return request_json(
        method,
        settings.github_api_url + path,
        token=settings.github_token,
        body=body,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        expected=expected,
    )


def wait_for_operation(
    settings: Settings, operation_id: str, timeout: int = 300, *, retrying: bool = False
) -> Any:
    """Wait for success. With retrying, failed is a backoff retry, not an end."""
    terminal = {"succeeded", "blocked"} if retrying else TERMINAL_OPERATION_STATES
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        operation = postgrip_request(
            settings,
            "GET",
            f"/api/v1/services/configuration-operations/{urllib.parse.quote(operation_id)}",
        )
        state = operation.get("state")
        if state in terminal:
            if state != "succeeded":
                raise LiveAdoptionError(
                    f"configuration operation ended in {state}: "
                    f"{operation.get('lastErrorCode', 'UNKNOWN')}"
                )
            return operation
        time.sleep(2)
    raise LiveAdoptionError("configuration operation wait timed out")


def find_repository(settings: Settings, repository_id: int, timeout: int = 180) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cursor = ""
        for _ in range(100):
            query = {"limit": "100"}
            if cursor:
                query["cursor"] = cursor
            page = postgrip_request(
                settings,
                "GET",
                "/api/v1/services/integrations/github/repositories?"
                + urllib.parse.urlencode(query),
            )
            for repository in page.get("items", []):
                if repository.get("id") == repository_id:
                    return repository
            cursor = page.get("nextCursor", "")
            if not cursor:
                break
        time.sleep(3)
    raise LiveAdoptionError("created repository did not appear in PostGrip discovery")


def create_project(
    settings: Settings, repository_name: str, branch: str, suffix: str
) -> tuple[str, str]:
    """Create the run's project on the repository.

    Returns the project ID and its environment's configuration operation.
    """
    catalog = postgrip_request(settings, "GET", "/api/v1/services?limit=1")
    slug = f"sdk-adoption-{suffix[:8]}"
    created = postgrip_request(
        settings,
        "POST",
        "/api/v1/services/projects",
        body={
            "name": slug,
            "slug": slug,
            "deploymentMode": "docker",
            "projectType": "web",
            "defaultWorkerId": settings.worker_id,
            "repository": {
                "provider": "github",
                "repoOwner": settings.github_org,
                "repoName": repository_name,
                "defaultBranch": branch,
            },
        },
        etag=catalog["catalogEtag"],
        expected=(201,),
    )
    project = created["project"]
    # The environment comes first: an adoption preview needs an assigned
    # Worker. Its configuration retries until adoption switches the project
    # to the App's global webhook.
    environment = postgrip_request(
        settings,
        "POST",
        f"/api/v1/services/project/{project['id']}/environments",
        body={
            "name": f"{slug}-production",
            "kind": "production",
            "branchPattern": branch,
            "assignedWorkerId": settings.worker_id,
        },
        etag=project["etag"],
        expected=(201,),
    )
    return project["id"], environment.get("configurationOperationId", "")


def refresh_credential(settings: Settings) -> None:
    repository = postgrip_request(
        settings,
        "GET",
        f"/api/v1/services/project/{settings.project_id}/repository",
    )
    result = postgrip_request(
        settings,
        "POST",
        f"/api/v1/services/project/{settings.project_id}/repository/credentials/source-access/refresh",
        etag=repository["etag"],
        expected=(202,),
    )
    wait_for_operation(settings, result["configurationOperationId"])


def wait_for_deployment(
    settings: Settings, commit_sha: str, previous_ids: set[str], timeout: int = 300
) -> Any:
    deadline = time.monotonic() + timeout
    path = f"/api/v1/services/project/{settings.project_id}/deployments?limit=100"
    while time.monotonic() < deadline:
        page = postgrip_request(settings, "GET", path)
        for deployment in page.get("items", []):
            if (
                deployment.get("id") not in previous_ids
                and deployment.get("commitSha") == commit_sha
                and deployment.get("triggerKind") == "github"
            ):
                return deployment
        time.sleep(3)
    raise LiveAdoptionError("signed GitHub push did not queue the expected deployment")


def run_lifecycle(settings: Settings, mode: str) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:16]
    repository_name = SAFE_REPOSITORY_PREFIX + suffix
    environment_operation = ""
    repository_id: int | None = None
    try:
        created = github_request(
            settings,
            "POST",
            f"/orgs/{urllib.parse.quote(settings.github_org)}/repos",
            body={
                "name": repository_name,
                "private": True,
                "auto_init": True,
                "description": "Disposable PostGrip GitHub adoption conformance fixture",
            },
            expected=(201,),
        )
        repository_id = int(created["id"])
        discovered = find_repository(settings, repository_id)
        if discovered.get("missingPermissions"):
            raise LiveAdoptionError("GitHub App installation lacks required permissions")
        if settings.worker_id:
            project_id, environment_operation = create_project(
                settings, repository_name, discovered["defaultBranch"], suffix
            )
            settings = replace(settings, project_id=project_id)

        preview = postgrip_request(
            settings,
            "POST",
            f"/api/v1/services/project/{settings.project_id}/repository/github/adoption-preview",
            body={"repositoryId": repository_id, "automaticDeployments": True},
            expected=(201,),
        )
        if preview.get("state") != "ready":
            raise LiveAdoptionError("GitHub adoption preview was blocked")
        operation = postgrip_request(
            settings,
            "POST",
            f"/api/v1/services/project/{settings.project_id}/repository/github/adopt",
            body={
                "previewId": preview["id"],
                "previewDigest": preview["digest"],
                "repositoryEtag": preview["repositoryEtag"],
            },
            etag=preview["repositoryEtag"],
            expected=(202,),
        )
        wait_for_operation(settings, operation["id"])
        if environment_operation:
            # Retries back off up to 320 s, so allow a few after adoption.
            wait_for_operation(settings, environment_operation, 900, retrying=True)

        if settings.wait_for_expiry:
            time.sleep(settings.expiry_wait_seconds)

        deployments = postgrip_request(
            settings,
            "GET",
            f"/api/v1/services/project/{settings.project_id}/deployments?limit=100",
        )
        previous_ids = {item["id"] for item in deployments.get("items", [])}
        content = base64.b64encode(
            b"# Disposable PostGrip live fixture\n\nCreated by the isolated adoption suite.\n"
        ).decode()
        commit = github_request(
            settings,
            "PUT",
            f"/repos/{urllib.parse.quote(settings.github_org)}/{repository_name}/contents/postgrip-live.md",
            body={
                "message": "test: trigger PostGrip automatic deployment",
                "content": content,
            },
            expected=(201,),
        )
        deployment = wait_for_deployment(
            settings, commit["commit"]["sha"], previous_ids
        )

        # Two explicit refreshes prove repeated mint/push semantics. With
        # POSTGRIP_GITHUB_LIVE_WAIT_FOR_EXPIRY=true, the commit above occurs
        # after the original token's GitHub lifetime, proving the background
        # rotation also kept deploys usable.
        refresh_credential(settings)
        refresh_credential(settings)
        return {
            "mode": mode,
            "projectId": settings.project_id,
            "repositoryId": repository_id,
            "operationId": operation["id"],
            "deploymentId": deployment["id"],
            "waitedPastOriginalExpiry": settings.wait_for_expiry,
            "credentialRefreshes": 2,
            "cleanup": "pending",
        }
    finally:
        if repository_id is not None:
            if not repository_name.startswith(SAFE_REPOSITORY_PREFIX):
                raise LiveAdoptionError("refusing unsafe GitHub repository cleanup")
            github_request(
                settings,
                "DELETE",
                f"/repos/{urllib.parse.quote(settings.github_org)}/{repository_name}",
                expected=(204,),
            )


def self_test() -> None:
    base = {
        "POSTGRIP_URL": "https://postgrip.example.test",
        "POSTGRIP_TOKEN": "redacted",
        "POSTGRIP_GITHUB_LIVE_PROJECT_ID": "00000000-0000-4000-8000-000000000001",
        "POSTGRIP_GITHUB_TEST_TOKEN": "redacted",
        "POSTGRIP_GITHUB_TEST_ORG": "postgrip-disposable",
        "POSTGRIP_GITHUB_LIVE_DISPOSABLE": "true",
    }
    settings = load_settings(base)
    assert settings.github_org == "postgrip-disposable"
    try:
        load_settings({**base, "POSTGRIP_GITHUB_TEST_ORG": "postgrip-io"})
    except LiveAdoptionError:
        pass
    else:
        raise AssertionError("production organization guard did not fail")
    try:
        load_settings({**base, "POSTGRIP_GITHUB_LIVE_DISPOSABLE": "false"})
    except LiveAdoptionError:
        pass
    else:
        raise AssertionError("disposable guard did not fail")
    run_owned = {**base, "POSTGRIP_GITHUB_LIVE_WORKER_ID": base["POSTGRIP_GITHUB_LIVE_PROJECT_ID"]}
    del run_owned["POSTGRIP_GITHUB_LIVE_PROJECT_ID"]
    for environ, guard in (
        ({**base, "POSTGRIP_GITHUB_LIVE_WORKER_ID": base["POSTGRIP_TOKEN"]}, "project-or-worker"),
        (run_owned, "stage lease"),
    ):
        try:
            load_settings(environ)
        except LiveAdoptionError:
            pass
        else:
            raise AssertionError(f"{guard} guard did not fail")
    assert load_settings({**run_owned, "POSTGRIP_LIVE_STAGE_LEASE": "lease"}).worker_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("nightly", "pre-release"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print("GitHub adoption live-suite safety self-test passed")
            return 0
        if not args.mode:
            raise LiveAdoptionError("--mode is required")
        settings = load_settings(os.environ)
        if args.validate_only:
            print(json.dumps({"mode": args.mode, "configuration": "valid"}))
            return 0
        result = run_lifecycle(settings, args.mode)
        result["cleanup"] = "completed"
        print(json.dumps(result, sort_keys=True))
        return 0
    except LiveAdoptionError as exc:
        print(f"GitHub adoption live suite failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
