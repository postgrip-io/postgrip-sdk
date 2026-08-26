#!/usr/bin/env python3
"""Run every operation through each language SDK against recorded fixtures."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "test" / "fixtures"
TOKEN = "pgt_recorded_sdk_token"
ACCESS_TOKEN = "pga_recorded_agent_access"
SIGNING_SEED = bytes(range(32))
SIGNING_KEY = base64.b64encode(SIGNING_SEED).decode("ascii")
PLANES = ("agent", "worker", "service")
LANGUAGES = ("go", "typescript", "python")


@dataclass(frozen=True)
class Case:
    operation_id: str
    plane: str
    method: str
    path_template: str
    auth_lane: str
    signing: str | None
    protocol: str
    fixture: dict[str, Any]

    @property
    def path(self) -> str:
        value = self.path_template
        for name, parameter in self.fixture["request"]["pathParameters"].items():
            value = value.replace("{" + name + "}", quote(str(parameter), safe=""))
        return value


class Recorder:
    def __init__(self, cases: list[Case]) -> None:
        self.cases = sorted(cases, key=lambda case: case.path_template.count("{"))
        self.failures: queue.Queue[str] = queue.Queue()
        self.counts: dict[str, int] = {}
        self.language = ""
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle_request(self) -> None:
                split = urlsplit(self.path)
                case = recorder.match(self.command, split.path)
                if case is None:
                    recorder.failures.put(
                        f"{recorder.language}: unmatched request {self.command} {split.path}"
                    )
                    self.send_error(500)
                    return
                body = self.read_body()
                failures = recorder.validate(case, split.query, self.headers, body)
                if failures:
                    for failure in failures:
                        recorder.failures.put(
                            f"{recorder.language}/{case.plane}/{case.operation_id}: {failure}"
                        )
                    payload = b'{"code":"CONFORMANCE_FAILED","message":"recording mismatch","requestId":"req_recorded"}'
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                key = f"{recorder.language}:{case.operation_id}"
                recorder.counts[key] = recorder.counts.get(key, 0) + 1
                response = case.fixture["response"]
                response_body = response["body"]
                encoded = b"" if response_body is None else json.dumps(
                    response_body, separators=(",", ":"), sort_keys=True
                ).encode("utf-8")
                self.send_response(response["status"])
                for name, value in response["headers"].items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                if encoded and self.command != "HEAD":
                    self.wfile.write(encoded)

            def read_body(self) -> bytes:
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    chunks: list[bytes] = []
                    while True:
                        line = self.rfile.readline().strip().split(b";", 1)[0]
                        size = int(line, 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        chunks.append(self.rfile.read(size))
                        self.rfile.read(2)
                    return b"".join(chunks)
                length = int(self.headers.get("Content-Length", "0"))
                return self.rfile.read(length) if length else b""

            do_GET = handle_request
            do_POST = handle_request
            do_PUT = handle_request
            do_PATCH = handle_request
            do_DELETE = handle_request
            do_HEAD = handle_request
            do_OPTIONS = handle_request

            def log_message(self, _format: str, *args: object) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> Recorder:
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def match(self, method: str, path: str) -> Case | None:
        for case in self.cases:
            if case.method != method:
                continue
            pattern = re.escape(case.path_template)
            pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", pattern)
            if re.fullmatch(pattern, path):
                return case
        return None

    def validate(
        self,
        case: Case,
        raw_query: str,
        headers: Any,
        body: bytes,
    ) -> list[str]:
        failures: list[str] = []
        expected_query = {
            name: [wire_value(item) for item in value]
            if isinstance(value, list)
            else [wire_value(value)]
            for name, value in case.fixture["request"]["query"].items()
        }
        actual_query = parse_qs(raw_query, keep_blank_values=True)
        if actual_query != expected_query:
            failures.append(f"query {actual_query!r}, want {expected_query!r}")
        for name, value in case.fixture["request"]["headers"].items():
            if headers.get(name) != value:
                failures.append(f"header {name}={headers.get(name)!r}, want {value!r}")
        authorization = headers.get("Authorization")
        if case.auth_lane in {"management", "worker-management", "service-management"}:
            expected_authorization = f"Bearer {TOKEN}"
        elif case.auth_lane in {"agent", "either"}:
            expected_authorization = f"Bearer {ACCESS_TOKEN}"
        else:
            expected_authorization = None
        if authorization != expected_authorization:
            failures.append(
                f"authorization class mismatch: present={authorization is not None}, "
                f"expected={expected_authorization is not None}"
            )
        request = case.fixture["request"]
        if request["streamBodyBase64"] is not None:
            expected_body = base64.b64decode(request["streamBodyBase64"])
            if body != expected_body:
                failures.append("streaming request body differs")
            if headers.get_content_type() != "application/gzip":
                failures.append("archive upload content type differs")
        elif request["body"] is None:
            if body:
                failures.append("body was sent for a bodyless operation")
        else:
            try:
                actual_body = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                failures.append("request body is not valid JSON")
            else:
                if actual_body != request["body"]:
                    failures.append(f"body {actual_body!r}, want {request['body']!r}")
            if headers.get_content_type() != "application/json":
                failures.append("JSON request content type differs")
        if case.signing == "agent-task-v1":
            failures.extend(validate_signature(case.method, case.path, raw_query, body, headers))
        return failures


def validate_signature(method: str, path: str, query: str, body: bytes, headers: Any) -> list[str]:
    failures: list[str] = []
    timestamp_value = headers.get("X-Agent-Signature-Timestamp")
    signature_value = headers.get("X-Agent-Signature")
    key_id = headers.get("X-Agent-Signature-Key-Id")
    try:
        timestamp = int(timestamp_value)
    except (TypeError, ValueError):
        return ["missing signature timestamp"]
    if abs(time.time() - timestamp) > 300:
        failures.append("signature timestamp is outside the accepted skew")
    private_key = Ed25519PrivateKey.from_private_bytes(SIGNING_SEED)
    public_key = private_key.public_key()
    raw_public = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    expected_key_id = hashlib.sha256(raw_public).hexdigest()[:16]
    if key_id != expected_key_id:
        failures.append("signature key ID differs")
    canonical = "\n".join(
        (
            "agent-task-v1",
            method.upper(),
            path,
            query,
            str(timestamp),
            base64.b64encode(hashlib.sha256(body).digest()).decode("ascii"),
            "",
        )
    ).encode("utf-8")
    try:
        public_key.verify(base64.b64decode(signature_value), canonical)
    except Exception:
        failures.append("agent-task-v1 signature verification failed")
    return failures


def wire_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def load_cases(selected_planes: tuple[str, ...]) -> list[Case]:
    inventory = json.loads((ROOT / "test" / "operation-inventory.json").read_text(encoding="utf-8"))
    ownership = json.loads((ROOT / "test" / "operation-tests.json").read_text(encoding="utf-8"))["operations"]
    cases: list[Case] = []
    for row in inventory["operations"]:
        if row["plane"] not in selected_planes:
            continue
        fixture_path = FIXTURES / ownership[row["operationId"]]["fixture"]
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases.append(
            Case(
                operation_id=row["operationId"], plane=row["plane"], method=row["method"],
                path_template=row["path"], auth_lane=row["authLane"], signing=row["signing"],
                protocol=row["protocol"], fixture=fixture,
            )
        )
    return cases


def run(command: list[str], *, cwd: Path, environment: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plane", choices=("all", *PLANES), default="all")
    parser.add_argument("--mode", choices=("recorded",), default="recorded")
    args = parser.parse_args()
    selected_planes = PLANES if args.plane == "all" else (args.plane,)
    cases = load_cases(selected_planes)
    environment = os.environ.copy()
    environment.update(
        {
            "POSTGRIP_TOKEN": TOKEN,
            "POSTGRIP_AGENT_ACCESS_TOKEN": ACCESS_TOKEN,
            "POSTGRIP_AGENT_SIGNING_PRIVATE_KEY": SIGNING_KEY,
            "PYTHONPATH": str(ROOT / "python" / "src"),
        }
    )
    commands = {
        "go": (
            ["go", "run", "../test/runners/go/main.go"],
            ROOT / "go",
        ),
        "typescript": (
            ["bun", "run", str(ROOT / "test" / "runners" / "typescript" / "recorded.ts")],
            ROOT / "typescript",
        ),
        "python": (
            [sys.executable, str(ROOT / "test" / "runners" / "python" / "recorded.py")],
            ROOT,
        ),
    }
    failures: list[str] = []
    custom = {case.operation_id for case in cases if case.operation_id == "connectSandboxSession"}
    normal_ids = {case.operation_id for case in cases} - custom
    with Recorder(cases) as recorder:
        for language in LANGUAGES:
            recorder.language = language
            command, cwd = commands[language]
            completed = run(
                [
                    *command,
                    "--base-url", recorder.url,
                    "--fixture-root", str(FIXTURES),
                    "--plane", args.plane,
                ],
                cwd=cwd,
                environment=environment,
            )
            if completed.returncode != 0:
                output = (completed.stderr or completed.stdout).replace(TOKEN, "[REDACTED]").replace(ACCESS_TOKEN, "[REDACTED]")
                failures.append(f"{language} runner exited {completed.returncode}: {output.strip()}")
                continue
            try:
                result = json.loads(completed.stdout)
            except json.JSONDecodeError:
                failures.append(f"{language} runner returned invalid JSON: {completed.stdout!r}")
                continue
            reported = set(result.get("operations", [])) & normal_ids
            if reported != normal_ids:
                failures.append(
                    f"{language} operation report differs: missing={sorted(normal_ids - reported)}, "
                    f"extra={sorted(reported - normal_ids)}"
                )
            for operation_id in normal_ids:
                count = recorder.counts.get(f"{language}:{operation_id}", 0)
                if count != 1:
                    failures.append(f"{language}/{operation_id}: recorded {count} requests, want 1")
        while not recorder.failures.empty():
            failures.append(recorder.failures.get())

    if custom:
        protocol_commands = {
            "go": (["go", "test", "./agent/client", "-run", "TestOpenSandboxSession"], ROOT / "go"),
            "typescript": (["bunx", "vitest", "run", "test/agent/sandbox.test.ts"], ROOT / "typescript"),
            "python": (
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "agent.test_python_sdk.SandboxClientDetailsTest.test_relay_dial_carries_configured_headers",
                ],
                ROOT / "python" / "test",
            ),
        }
        for language, (command, cwd) in protocol_commands.items():
            completed = run(command, cwd=cwd, environment=environment)
            if completed.returncode != 0:
                failures.append(f"{language} WebSocket protocol runner failed: {completed.stderr.strip() or completed.stdout.strip()}")

    if failures:
        print("Recorded endpoint conformance failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        f"Recorded endpoint conformance passed: {len(cases)} operations x "
        f"{len(LANGUAGES)} languages ({len(cases) * len(LANGUAGES)} ownership checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
