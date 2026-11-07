from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from _http_fakes import FakeResponse
from postgrip.agent import AgentAPIError
from postgrip.agent._connection import Connection
from postgrip.agent.client import Client

EXPIRES = "2999-01-01T00:00:00Z"


def http_error(status: int, body: object, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("http://agent.test", status, "failed", headers, BytesIO(json.dumps(body).encode()))


class Recorder:
    """Stands in for the Agent module's urlopen, answering scripted responses in order."""

    def __init__(self, *responses: object):
        self.responses = list(responses)
        self.requests: list[object] = []

    def __call__(self, request: object, timeout: float | None = None) -> FakeResponse:
        self.requests.append(request)
        value = self.responses.pop(0) if self.responses else {"id": "task-1"}
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)

    def keys(self) -> list[str | None]:
        return [request.get_header("Idempotency-key") for request in self.requests]  # type: ignore[attr-defined]


def connection(*, managed: bool = False) -> Connection:
    options = {"agent_access_token": "delegated-1", "agent_access_expires_at": EXPIRES} if managed else {}
    return Connection("http://agent.test", insecure_development=True, auth_token="management-token",
                      enable_retries=True, **options)  # type: ignore[arg-type]


class CancelTaskTests(unittest.TestCase):
    def test_posts_the_reason_to_the_cancel_path_and_returns_the_task(self) -> None:
        cancelled = {"id": "task-1", "state": "failed", "error": "task cancelled: superseded",
                     "result": {"failure": {"type": "TaskCancelled", "message": "superseded", "non_retryable": True}}}
        recorder = Recorder(cancelled, cancelled)
        with patch("postgrip.agent._connection.urlopen", recorder):
            tasks = Client(connection()).task
            self.assertEqual(tasks.cancel("task-1", reason="superseded"), cancelled)
            tasks.cancel("task-1")
        self.assertEqual(
            [(request.full_url, request.data) for request in recorder.requests],  # type: ignore[attr-defined]
            [("http://agent.test/api/v1/tasks/task-1/cancel", b'{"reason":"superseded"}'),
             ("http://agent.test/api/v1/tasks/task-1/cancel", b"{}")],
        )
        self.assertEqual(recorder.requests[0].get_header("Authorization"), "Bearer management-token")  # type: ignore[attr-defined]
        self.assertEqual(recorder.keys(), [None, None])

    def test_a_finished_task_is_a_task_terminal_conflict_answered_once(self) -> None:
        recorder = Recorder(http_error(409, {"code": "TASK_TERMINAL", "message": "task is already terminal",
                                             "requestId": "req-1", "details": {"state": "succeeded"}}))
        with patch("postgrip.agent._connection.urlopen", recorder), self.assertRaises(AgentAPIError) as raised:
            connection().cancel_task("task-1")
        self.assertEqual((raised.exception.status, raised.exception.code), (409, "TASK_TERMINAL"))
        self.assertEqual(raised.exception.details, {"state": "succeeded"})
        self.assertEqual(len(recorder.requests), 1)


class OptionalIdempotencyKeyTests(unittest.TestCase):
    def test_is_sent_on_task_sends_and_signals_only_when_given(self) -> None:
        started = {"workflow": {"id": "order-42", "type": "OrderWorkflow"}, "task": {"id": "task-9"}, "signal": {"id": "evt-1"}}
        recorder = Recorder({"id": "task-1"}, {"id": "task-1"}, {"id": "evt-1"}, {"id": "evt-2"}, started, {"id": "task-1"})
        with patch("postgrip.agent._connection.urlopen", recorder):
            conn = connection(managed=True)
            client = Client(conn)
            client.task.enqueue(type="noop", idempotency_key="ci-run-4512")
            client.task.noop()
            handle = client.workflow.get_handle("order-42")
            handle.signal_sync("approve", idempotency_key="approve-1")
            asyncio.run(handle.signal("approve", 1, idempotency_key="approve-2"))
            client.workflow.signal_with_start("OrderWorkflow", signal="approve", workflow_id="order-42",
                                              idempotency_key="approve-3")
            conn.openapi.enqueue_task({"type": "noop"}, idempotency_key="raw-1")
        self.assertEqual(recorder.keys(), ["ci-run-4512", None, "approve-1", "approve-2", "approve-3", "raw-1"])
        self.assertEqual(json.loads(recorder.requests[3].data)["args"], [1])  # type: ignore[attr-defined]

    def test_is_checked_before_sending_and_makes_the_send_retryable(self) -> None:
        recorder = Recorder(http_error(503, {"code": "BUSY", "message": "busy"}, retry_after="0"), {"id": "task-1"})
        with patch("postgrip.agent._connection.urlopen", recorder), patch("postgrip._internal.transport.time.sleep"):
            tasks = Client(connection()).task
            with self.assertRaisesRegex(ValueError, "idempotency"):
                tasks.enqueue(type="noop", idempotency_key="not valid")
            self.assertEqual(recorder.requests, [])
            self.assertEqual(tasks.enqueue(type="noop", idempotency_key="ci-run-4512"), {"id": "task-1"})
        self.assertEqual(recorder.keys(), ["ci-run-4512", "ci-run-4512"])
        self.assertEqual(recorder.requests[0].data, recorder.requests[1].data)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
