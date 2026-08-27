#!/usr/bin/env python3
"""Execute every generated cURL example against a recording HTTP server."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlsplit

from _contracts import PLANES, snake
from generate_api_docs import load_inputs, operations, request_body, resolve
from _recording_server import RecordingServerLifecycle


ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference"
TOKEN = "pgt_recorded_conformance_token"


@dataclass(frozen=True)
class ExpectedRequest:
    operation_id: str
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: Any
    authenticated: bool


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes


class RecordingServer(RecordingServerLifecycle):
    def __init__(self) -> None:
        self.records: queue.Queue[RecordedRequest] = queue.Queue()
        records = self.records

        class Handler(BaseHTTPRequestHandler):
            def record(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b""
                target = urlsplit(self.path)
                records.put(
                    RecordedRequest(
                        method=self.command,
                        path=target.path,
                        query=parse_qs(target.query, keep_blank_values=True),
                        headers={name.lower(): value for name, value in self.headers.items()},
                        body=body,
                    )
                )
                if self.command == "POST" and target.path == "/api/v1/workers":
                    response = json.dumps({
                        "worker": {"id": "11111111-1111-4111-8111-111111111111"},
                        "etag": '"worker-etag"',
                        "bootstrap": {
                            "enrollmentExpiresAt": "2026-08-27T00:00:00Z",
                            "attestationExpiresAt": "2026-08-27T00:00:00Z",
                        },
                    }).encode() + b"\n"
                    status = 201
                else:
                    response = b"{}\n"
                    status = 200
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.send_header("X-Request-Id", "req_recorded")
                self.end_headers()
                self.wfile.write(response)

            do_GET = record
            do_POST = record
            do_PUT = record
            do_PATCH = record
            do_DELETE = record
            do_HEAD = record
            do_OPTIONS = record

            def log_message(self, _format: str, *args: object) -> None:
                return None

        super().__init__(Handler)


def shell_block(page: str) -> str:
    match = re.search(r"```sh\n(.*?)\n```", page, re.DOTALL)
    if not match:
        raise ValueError("generated page has no shell block")
    return match.group(1)


def parameter_environment(
    document: dict[str, Any], operation: dict[str, Any]
) -> tuple[dict[str, str], str, dict[str, str], dict[str, str]]:
    environment: dict[str, str] = {}
    path = operation["path"]
    query: dict[str, str] = {}
    headers: dict[str, str] = {}
    parameters = [resolve(document, item) for item in operation["parameters"]]
    for parameter in parameters:
        if not parameter.get("required"):
            continue
        name = parameter["name"]
        variable = "POSTGRIP_" + snake(name).upper()
        location = parameter["in"]
        if location == "path":
            value = "11111111-1111-4111-8111-111111111111"
            environment[variable] = value
            path = path.replace("{" + name + "}", value)
        elif location == "query":
            value = "recorded-query"
            environment[variable] = value
            query[name] = value
        elif location == "header":
            if name.lower() == "idempotency-key":
                value = f"recorded-{operation['operationId']}"
            elif name.lower() == "if-match":
                value = '"revision:7"'
            else:
                value = "recorded-header"
            environment[variable] = value
            headers[name.lower()] = value
    return environment, path, query, headers


def expected_requests(
    selected_planes: tuple[str, ...],
) -> list[tuple[str, ExpectedRequest, str, dict[str, str]]]:
    contracts, _notes, ownership = load_inputs()
    inventory = json.loads((ROOT / "test" / "operation-inventory.json").read_text(encoding="utf-8"))
    bundle = inventory["contractBundleDigest"]
    selected: list[tuple[str, ExpectedRequest, str, dict[str, str]]] = []
    for plane in selected_planes:
        document = contracts[plane]
        for operation in operations(document):
            operation_id = operation["operationId"]
            if not ownership[operation_id]["curlEligible"]:
                continue
            environment, path, query, headers = parameter_environment(document, operation)
            _content_type, _schema, body = request_body(document, operation)
            page = REFERENCE / bundle / plane / f"{operation_id}.md"
            selected.append(
                (
                    plane,
                    ExpectedRequest(
                        operation_id=operation_id,
                        method=operation["method"],
                        path=path,
                        query=query,
                        headers=headers,
                        body=body,
                        authenticated=bool(operation.get("x-postgrip-accepted-credentials", [])),
                    ),
                    shell_block(page.read_text(encoding="utf-8")),
                    environment,
                )
            )
    return selected


def validate(expected: ExpectedRequest, recorded: RecordedRequest) -> list[str]:
    failures: list[str] = []
    if recorded.method != expected.method:
        failures.append(f"method {recorded.method}, want {expected.method}")
    if recorded.path != expected.path:
        failures.append(f"path {recorded.path!r}, want {expected.path!r}")
    for name, value in expected.query.items():
        if recorded.query.get(name) != [value]:
            failures.append(f"query {name}={recorded.query.get(name)!r}, want {[value]!r}")
    for name, value in expected.headers.items():
        if recorded.headers.get(name) != value:
            failures.append(f"header {name}={recorded.headers.get(name)!r}, want {value!r}")
    authorization = recorded.headers.get("authorization")
    if expected.authenticated and authorization != f"Bearer {TOKEN}":
        failures.append("missing or incorrect bearer authentication")
    if not expected.authenticated and authorization is not None:
        failures.append("unexpected bearer authentication")
    if expected.body is not None:
        try:
            actual_body = json.loads(recorded.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            failures.append("request body is not valid JSON")
        else:
            if actual_body != expected.body:
                failures.append(f"body {actual_body!r}, want {expected.body!r}")
        if recorded.headers.get("content-type") != "application/json":
            failures.append("JSON request is missing Content-Type: application/json")
    elif recorded.body:
        failures.append("operation without a body sent bytes")
    return failures


def curl_version(curl: str) -> tuple[int, int]:
    output = subprocess.run([curl, "--version"], check=True, capture_output=True, text=True).stdout
    match = re.match(r"curl (\d+)\.(\d+)", output)
    if not match:
        raise RuntimeError("could not parse cURL version")
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plane", choices=("all", *PLANES), default="all")
    args = parser.parse_args()
    selected_planes = PLANES if args.plane == "all" else (args.plane,)
    real_curl = shutil.which("curl")
    if not real_curl:
        raise SystemExit("cURL is required")
    if curl_version(real_curl) < (7, 76):
        raise SystemExit("cURL 7.76 or newer is required")

    failures: list[str] = []
    cases = expected_requests(selected_planes)
    with RecordingServer() as recording, tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        wrapper = temporary / "curl"
        wrapper.write_text(
            "#!/bin/sh\nprintf '%s\\0' \"$@\" >\"$POSTGRIP_CURL_ARGV_CAPTURE\"\n"
            "exec \"$POSTGRIP_REAL_CURL\" \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        for plane, expected, script, case_environment in cases:
            capture = temporary / f"{expected.operation_id}.argv"
            environment = os.environ.copy()
            for variable in ("POSTGRIP_AGENT_URL", "POSTGRIP_WORKER_URL", "POSTGRIP_SERVICE_URL"):
                environment.pop(variable, None)
            environment.update(
                {
                    "PATH": f"{temporary}{os.pathsep}{environment.get('PATH', '')}",
                    "POSTGRIP_URL": recording.url,
                    "POSTGRIP_TOKEN": TOKEN,
                    "POSTGRIP_REAL_CURL": real_curl,
                    "POSTGRIP_CURL_ARGV_CAPTURE": str(capture),
                    **case_environment,
                }
            )
            if expected.operation_id == "createWorker":
                environment.update({
                    "POSTGRIP_WORKER_NAME": str(expected.body["name"]),
                    "POSTGRIP_WORKER_HOST": str(expected.body["host"]),
                    "POSTGRIP_BOOTSTRAP_STATE": str(temporary / "create-worker.secret.json"),
                    "POSTGRIP_WORKER_RECEIPT": str(temporary / "create-worker.receipt.json"),
                })
            completed = subprocess.run(
                ["bash", "-eu", "-o", "pipefail", "-c", script],
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
            label = f"{plane}/{expected.operation_id}"
            if completed.returncode != 0:
                stderr = completed.stderr.replace(TOKEN, "[REDACTED]").strip()
                failures.append(f"{label}: cURL exited {completed.returncode}: {stderr}")
                continue
            try:
                recorded = recording.records.get(timeout=5)
            except queue.Empty:
                failures.append(f"{label}: recording server received no request")
                continue
            if expected.operation_id == "createWorker":
                state = json.loads(Path(environment["POSTGRIP_BOOTSTRAP_STATE"]).read_text(encoding="utf-8"))
                expected = ExpectedRequest(
                    operation_id=expected.operation_id,
                    method=expected.method,
                    path=expected.path,
                    query=expected.query,
                    headers={**expected.headers, "idempotency-key": state["idempotencyKey"]},
                    body=state["request"],
                    authenticated=expected.authenticated,
                )
                if not Path(environment["POSTGRIP_WORKER_RECEIPT"]).is_file():
                    failures.append(f"{label}: safe Worker receipt was not persisted")
            failures.extend(f"{label}: {failure}" for failure in validate(expected, recorded))
            argv = capture.read_bytes().split(b"\0") if capture.is_file() else []
            if any(TOKEN.encode() in argument for argument in argv):
                failures.append(f"{label}: expanded token appeared in cURL argv")
            if any(b"Authorization:" in argument for argument in argv):
                failures.append(f"{label}: authorization header appeared in cURL argv")
            output = (completed.stdout + completed.stderr)
            if TOKEN in output:
                failures.append(f"{label}: token appeared in subprocess output")

    if failures:
        print("cURL conformance failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    by_plane = {
        plane: sum(
            1 for case_plane, _expected, _script, _environment in cases
            if case_plane == plane
        )
        for plane in selected_planes
    }
    summary = ", ".join(f"{plane}={count}" for plane, count in by_plane.items())
    print(f"cURL conformance passed: {len(cases)} operations ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
