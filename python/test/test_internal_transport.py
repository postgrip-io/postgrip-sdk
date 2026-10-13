from __future__ import annotations

from dataclasses import dataclass, replace
from email.message import Message
from io import BytesIO
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from _http_fakes import FakeOpener
from postgrip._internal.transport import APIErrorFields, Executor, PostGripAPIError, RetryConfig


@dataclass(frozen=True)
class Operation:
    operation_id: str = "testOperation"
    method: str = "GET"
    path: str = "/api/v1/test"
    auth_lane: str = "worker-management"
    safety: str = "read-only"
    retry: str = "bounded"
    signing: str = ""
    streaming_request: bool = False
    websocket: bool = False
    idempotency: str = "none"
    header_parameters: tuple[str, ...] = ()


def to_error(fields: APIErrorFields) -> PostGripAPIError:
    return PostGripAPIError(status=fields.status, code=fields.code, message=fields.message)


def executor(opener: FakeOpener) -> Executor:
    return Executor(
        plane="Test",
        base_url="https://api.example.com",
        opener=opener,  # type: ignore[arg-type]
        management_token="pgt_management",
        retry=RetryConfig(enabled=True, max_attempts=3, max_delay=0.001, retry_after_max=0.001),
        timeout=30.0,
        create_error=to_error,
    )


def busy() -> HTTPError:
    headers = Message()
    headers["Retry-After"] = "0"
    return HTTPError("https://api.example.com", 503, "busy", headers, BytesIO(json.dumps({"code": "BUSY"}).encode()))


class ExecutorTests(unittest.TestCase):
    def test_sends_the_management_bearer_on_every_management_lane(self) -> None:
        for lane in ("management", "worker-management", "service-management"):
            with self.subTest(lane):
                opener = FakeOpener([{}])
                executor(opener).request(replace(Operation(), auth_lane=lane))
                self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer pgt_management")

    def test_refuses_delegated_and_unknown_lanes_signing_and_adapters_before_sending(self) -> None:
        for operation, message in (
            (replace(Operation(), auth_lane="agent"), "unsupported auth lane agent"),
            (replace(Operation(), auth_lane="either"), "unsupported auth lane either"),
            (replace(Operation(), auth_lane="unknown"), "unsupported auth lane unknown"),
            (replace(Operation(), signing="agent-task-v1"), "requires request signing"),
            (replace(Operation(), streaming_request=True), "protocol adapter"),
            (replace(Operation(), websocket=True), "protocol adapter"),
        ):
            with self.subTest(message):
                opener = FakeOpener([])
                with self.assertRaisesRegex(ValueError, message):
                    executor(opener).request(operation)
                self.assertEqual(opener.requests, [])

    def test_never_retries_a_protocol_operation(self) -> None:
        opener = FakeOpener([busy(), {}])
        with self.assertRaises(PostGripAPIError):
            executor(opener).request(replace(Operation(), safety="protocol"), idempotency_key="key-1")
        self.assertEqual(len(opener.requests), 1)

    def test_forwards_idempotency_and_if_match_only_where_declared(self) -> None:
        opener = FakeOpener([{}, {}])
        executor(opener).request(Operation(), idempotency_key="key-1", if_match='"etag"')
        declared = replace(Operation(), header_parameters=("Idempotency-Key", "If-Match"))
        executor(opener).request(declared, idempotency_key="key-1", if_match='"etag"')
        self.assertEqual([r.get_header("Idempotency-key") for r in opener.requests], [None, "key-1"])
        self.assertEqual([r.get_header("If-match") for r in opener.requests], [None, '"etag"'])

    def test_retries_an_eligible_read(self) -> None:
        opener = FakeOpener([busy(), {"ok": True}])
        with patch("postgrip._internal.transport.time.sleep"):
            self.assertEqual(executor(opener).request(Operation()), {"ok": True})
        self.assertEqual(len(opener.requests), 2)


if __name__ == "__main__":
    unittest.main()
