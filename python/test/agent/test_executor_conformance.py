from __future__ import annotations

import base64
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import re
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from _http_fakes import FakeResponse
from postgrip import PostGrip
from postgrip._internal.transport import PostGripAPIError
from postgrip.agent import AgentAPIError
from postgrip.agent._connection import Connection
from postgrip.agent.errors import is_terminal_task_mutation
from postgrip.agent.openapi import OperationId, resolve_openapi_operation

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "agent-openapi.json"
FRESH = {"agentId": "agent-1", "accessToken": "delegated-1", "refreshToken": "refresh-1",
         "accessExpiresAt": "2999-01-01T00:00:00Z"}
SIGNING_KEY = base64.b64encode(bytes([7]) * 32).decode()


def contract_operations() -> list[dict[str, object]]:
    """Every Agent operation the executor runs, with its annotations, read from the contract."""
    spec = json.loads(CONTRACT.read_text())
    operations = []
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            parameters = {name: f"p-{name}" for name in re.findall(r"\{(\w+)\}", path)}
            resolved = resolve_openapi_operation(OperationId(operation["operationId"]), parameters)
            operations.append({
                "id": resolved.operation_id, "method": method.upper(), "path": path, "parameters": parameters,
                "lane": operation["x-postgrip-auth-lane"], "safety": operation["x-postgrip-safety"],
                "retry": operation["x-postgrip-retry"], "signing": operation.get("x-postgrip-request-signing", ""),
                "has_body": "requestBody" in operation,
                "adapter": resolved.streaming_request or resolved.websocket,
            })
    return operations


def http_error(status: int, body: object, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("http://agent.test", status, "failed", headers, BytesIO(json.dumps(body).encode()))


class Recorder:
    """Stands in for the Agent module's urlopen, answering scripted responses in order."""

    def __init__(self, responses: list[object]):
        self.responses = responses
        self.requests: list[object] = []
        self.timeouts: list[float | None] = []

    def __call__(self, request: object, timeout: float | None = None) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        value = self.responses.pop(0) if self.responses else {}
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)


def connection(**options: object) -> Connection:
    return Connection("http://agent.test", insecure_development=True, auth_token="management-token", **options)  # type: ignore[arg-type]


def call(client: Connection, operation: dict[str, object]) -> object:
    return client.openapi.request(
        operation["id"],  # type: ignore[arg-type]
        {} if operation["has_body"] else None,
        path_parameters=operation["parameters"],  # type: ignore[arg-type]
    )


class AgentExecutorConformanceTests(unittest.TestCase):
    def test_covers_every_agent_operation_and_leaves_adapters_alone(self) -> None:
        operations = contract_operations()
        self.assertEqual(len(operations), 45)
        self.assertEqual(sorted(o["id"].value for o in operations if o["adapter"]),  # type: ignore[union-attr]
                         ["connectSandboxSession", "uploadWorkspace"])
        executed = [o for o in operations if not o["adapter"]]
        self.assertEqual(len([o for o in executed if o["retry"] == "bounded" and o["safety"] == "read-only"]), 18)
        self.assertEqual(len([o for o in executed if o["signing"]]), 5)

    def test_each_operation_follows_its_lane_signing_and_retry_annotations(self) -> None:
        delegated = {"agent_access_token": FRESH["accessToken"], "agent_refresh_token": FRESH["refreshToken"],
                     "agent_access_expires_at": FRESH["accessExpiresAt"], "agent_signing_private_key": SIGNING_KEY}
        for operation in contract_operations():
            if operation["adapter"]:
                continue
            eligible = operation["retry"] == "bounded" and operation["safety"] == "read-only" and not operation["signing"]
            with self.subTest(operation["id"].value):  # type: ignore[union-attr]
                recorder = Recorder([{}])
                with patch("postgrip.agent._connection.urlopen", recorder):
                    call(connection(headers={"Authorization": "Bearer configured"}, **delegated), operation)
                request = recorder.requests[-1]
                expected = {"public": None, "agent": "Bearer delegated-1", "either": "Bearer delegated-1",
                            "management": "Bearer configured"}[operation["lane"]]  # type: ignore[index]
                self.assertEqual(request.get_header("Authorization"), expected)  # type: ignore[attr-defined]
                self.assertEqual(request.get_header("Accept"), "application/json")  # type: ignore[attr-defined]
                self.assertEqual(request.get_header("User-agent"), "postgrip-agent-python")  # type: ignore[attr-defined]
                self.assertEqual(request.has_header("X-agent-signature"), bool(operation["signing"]))  # type: ignore[attr-defined]

                if operation["lane"] != "agent":
                    plain = Recorder([{}])
                    with patch("postgrip.agent._connection.urlopen", plain):
                        call(connection(), operation)
                    self.assertEqual(plain.requests[-1].get_header("Authorization"),  # type: ignore[attr-defined]
                                     None if operation["lane"] == "public" else "Bearer management-token")

                busy = http_error(503, {"code": "BUSY"}, "0")
                retrying = Recorder([busy, {}])
                with patch("postgrip.agent._connection.urlopen", retrying):
                    if eligible:
                        call(connection(enable_retries=True, **delegated), operation)
                        self.assertEqual(len(retrying.requests), 2)
                    else:
                        with self.assertRaises(AgentAPIError):
                            call(connection(enable_retries=True, **delegated), operation)
                        self.assertEqual(len(retrying.requests), 1)

    def test_agent_api_error_text_and_repr_exclude_server_content(self) -> None:
        body = {"code": "NOT_FOUND", "message": "secret detail", "requestId": "req-1", "details": {"taskId": "t"}}
        with patch("postgrip.agent._connection.urlopen", Recorder([http_error(404, body)])):
            with self.assertRaises(AgentAPIError) as raised:
                connection().get_task("t")
        error = raised.exception
        self.assertIsInstance(error, PostGripAPIError)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual((error.status, error.code, error.request_id, error.method, error.route),
                         (404, "NOT_FOUND", "req-1", "GET", "/api/v1/tasks/t"))
        self.assertEqual(str(error), 'postgrip-agent: "GET" "/api/v1/tasks/t" -> 404 Not Found')
        self.assertNotIn("secret", str(error))
        self.assertNotIn("secret", repr(error))
        self.assertIn(b"secret detail", error.response_body)

    def test_malformed_success_body_reports_only_the_request(self) -> None:
        with patch("postgrip.agent._connection.urlopen", Recorder([b'{"secret": oops'])):
            with self.assertRaises(RuntimeError) as raised:
                connection().get_task("t")
        self.assertEqual(str(raised.exception), "postgrip-agent: GET /api/v1/tasks/t -> 200 (parse failed)")
        self.assertIsNone(raised.exception.__cause__)

    def test_workspace_upload_failures_are_typed_without_server_text(self) -> None:
        from postgrip.agent.sandbox import SandboxClient

        failure = http_error(413, {"code": "TOO_LARGE", "message": "archive secret"})
        with patch("postgrip.agent._sandbox_transport.urlopen", Recorder([failure])):
            with self.assertRaises(AgentAPIError) as raised:
                SandboxClient(connection()).upload_workspace(b"archive")
        self.assertEqual((raised.exception.status, raised.exception.code, raised.exception.route),
                         (413, "TOO_LARGE", "/api/v1/workspaces"))
        self.assertNotIn("archive secret", str(raised.exception))

    def test_detects_terminal_and_unleased_task_mutations_from_the_409_envelope(self) -> None:
        def failure(status: int, message: str) -> BaseException:
            recorder = Recorder([http_error(status, {"code": "CONFLICT", "message": message})])
            with patch("postgrip.agent._connection.urlopen", recorder):
                try:
                    connection(agent_access_token="delegated-1", agent_access_expires_at=FRESH["accessExpiresAt"]
                               ).complete_task("task-1", "agent-1", {})
                except BaseException as error:  # noqa: BLE001
                    return error
            raise AssertionError("expected a failure")

        self.assertTrue(is_terminal_task_mutation(failure(409, "task is already terminal")))
        self.assertTrue(is_terminal_task_mutation(failure(409, "task is not leased by agent")))
        self.assertFalse(is_terminal_task_mutation(failure(409, "workflow exists")))
        self.assertFalse(is_terminal_task_mutation(failure(500, "task is already terminal")))

    def test_poll_keeps_gone_as_shutdown_and_gets_long_poll_headroom(self) -> None:
        recorder = Recorder([http_error(410, {"directive": {"reason": "drain"}})])
        with patch("postgrip.agent._connection.urlopen", recorder):
            response = connection(agent_access_token="delegated-1", agent_access_expires_at=FRESH["accessExpiresAt"]
                                  ).poll_task_response(namespace="default", queue="q", agent_id="agent-1", wait_seconds=25)
        self.assertEqual(response, {"directive": {"reason": "drain", "type": "shutdown"}})
        self.assertEqual(recorder.timeouts, [55])

    def test_raw_request_runs_under_the_matched_operation(self) -> None:
        recorder = Recorder([{"status": "ok"}])
        with patch("postgrip.agent._connection.urlopen", recorder):
            connection(headers={"Authorization": "Bearer configured"}).request("GET", "/healthz")
        self.assertIsNone(recorder.requests[0].get_header("Authorization"))  # type: ignore[attr-defined]

    def test_raw_request_refuses_absolute_urls_before_sending(self) -> None:
        recorder = Recorder([{}])
        with patch("postgrip.agent._connection.urlopen", recorder):
            for path in ("https://attacker.example/x", "//attacker.example/x"):
                with self.subTest(path), self.assertRaisesRegex(ValueError, "relative to the configured base URL"):
                    connection().request("GET", path, agent_auth=True)
        self.assertEqual(recorder.requests, [])

    def test_connection_headers_and_timeout_changes_apply_to_later_calls(self) -> None:
        client = connection()
        client.headers["X-Gateway"] = "rotated"
        client.timeout = 7
        recorder = Recorder([{"status": "ok"}])
        with patch("postgrip.agent._connection.urlopen", recorder):
            client.health()
        self.assertEqual(recorder.requests[0].get_header("X-gateway"), "rotated")  # type: ignore[attr-defined]
        self.assertEqual(recorder.timeouts, [7])

    def test_root_client_passes_retries_to_the_agent_plane(self) -> None:
        recorder = Recorder([http_error(503, {"code": "BUSY"}, "0"), {"status": "ok"}])
        with patch("postgrip.agent._connection.urlopen", recorder):
            client = PostGrip(base_url="http://agent.test", token="pgt", insecure_development=True, enable_retries=True)
            client.agent.connection.health()
        self.assertEqual(len(recorder.requests), 2)


if __name__ == "__main__":
    unittest.main()
