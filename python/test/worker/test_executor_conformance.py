from __future__ import annotations

from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import re
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from _http_fakes import FakeOpener
from postgrip._internal.transport import PostGripAPIError, parse_retry_after
from postgrip.worker import WorkerAPIError, WorkerClient
from postgrip.worker.openapi import OperationId

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "worker-openapi.json"


def contract_operations() -> list[dict[str, object]]:
    """Every Worker operation with the annotations the executor must follow, read from the contract."""
    spec = json.loads(CONTRACT.read_text())
    operations = []
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operations.append({
                "id": OperationId(operation["operationId"]),
                "method": method.upper(),
                "path": path,
                "auth_lane": operation["x-postgrip-auth-lane"],
                "safety": operation["x-postgrip-safety"],
                "idempotency": operation["x-postgrip-idempotency"],
                "retry": operation["x-postgrip-retry"],
                "has_body": "requestBody" in operation,
            })
    return operations


def busy() -> HTTPError:
    headers = Message()
    headers["Retry-After"] = "0"
    body = BytesIO(json.dumps({"code": "BUSY", "message": "busy", "requestId": "req-1"}).encode())
    return HTTPError("https://workers.example.com", 503, "Service Unavailable", headers, body)


def call(client: WorkerClient, operation: dict[str, object], key: str | None) -> object:
    path = str(operation["path"])
    return client.openapi.request(
        operation["id"],  # type: ignore[arg-type]
        {} if operation["has_body"] else None,
        path_parameters={name: f"p-{name}" for name in re.findall(r"\{(\w+)\}", path)},
        headers={"Idempotency-Key": key} if key else None,
    )


def client(opener: FakeOpener, *, enable_retries: bool = False) -> WorkerClient:
    return WorkerClient(base_url="https://workers.example.com", token="pgt_management",
                        opener=opener, enable_retries=enable_retries)  # type: ignore[arg-type]


class WorkerExecutorConformanceTests(unittest.TestCase):
    def test_covers_every_generated_worker_operation(self) -> None:
        self.assertEqual(len(contract_operations()), 21)

    def test_each_operation_follows_its_contract_annotations(self) -> None:
        for operation in contract_operations():
            key = "key-1" if operation["idempotency"] == "required" else None
            eligible = operation["retry"] == "bounded" and (operation["safety"] == "read-only" or key is not None)
            with self.subTest(operation["id"].value):  # type: ignore[union-attr]
                opener = FakeOpener([{}])
                call(client(opener), operation, key)
                request = opener.requests[0]
                self.assertEqual(request.get_method(), operation["method"])
                expected_auth = None if operation["auth_lane"] == "public" else "Bearer pgt_management"
                self.assertEqual(request.get_header("Authorization"), expected_auth)
                self.assertEqual(request.get_header("Idempotency-key"), key)
                self.assertEqual(request.get_header("Content-type"),
                                 "application/json" if operation["has_body"] else None)

                with patch("postgrip._internal.transport.time.sleep"):
                    retrying = FakeOpener([busy(), {}])
                    if eligible:
                        self.assertEqual(call(client(retrying, enable_retries=True), operation, key), {})
                        self.assertEqual(len(retrying.requests), 2)
                        self.assertEqual({r.get_header("Idempotency-key") for r in retrying.requests}, {key})
                    else:
                        with self.assertRaises(WorkerAPIError):
                            call(client(retrying, enable_retries=True), operation, key)
                        self.assertEqual(len(retrying.requests), 1)

                    disabled = FakeOpener([busy(), {}])
                    with self.assertRaises(WorkerAPIError):
                        call(client(disabled), operation, key)
                    self.assertEqual(len(disabled.requests), 1)

                if key:
                    missing = FakeOpener([{}])
                    with self.assertRaisesRegex(ValueError, "visible ASCII"):
                        call(client(missing), operation, None)
                    self.assertEqual(missing.requests, [])

    def test_error_keeps_its_fields_and_text_and_is_a_postgrip_api_error(self) -> None:
        headers = Message()
        headers["X-Request-ID"] = "req-header"
        body = BytesIO(json.dumps({"code": "NOT_FOUND", "message": "worker not found", "details": {"workerId": "w"}}).encode())
        opener = FakeOpener([HTTPError("https://workers.example.com", 404, "Not Found", headers, body)])
        with self.assertRaises(WorkerAPIError) as raised:
            client(opener).get("w")
        error = raised.exception
        self.assertIsInstance(error, PostGripAPIError)
        self.assertEqual((error.status, error.code, error.message, error.request_id, error.details),
                         (404, "NOT_FOUND", "worker not found", "req-header", {"workerId": "w"}))
        self.assertEqual(str(error), "postgrip-worker: NOT_FOUND (HTTP 404): worker not found")
        self.assertEqual(WorkerAPIError(status=1, code="c", message="m"), WorkerAPIError(status=1, code="c", message="m"))

    def test_empty_success_body_returns_none(self) -> None:
        self.assertIsNone(client(FakeOpener([b""])).get("w"))

    def test_retry_after_accepts_only_delta_seconds_or_an_http_date(self) -> None:
        self.assertEqual(parse_retry_after("120", 30.0), 30.0)
        self.assertEqual(parse_retry_after("0", 30.0), 0.0)
        for value in ("+5", "-5", "1.5", "1e1", "nan", "inf", ""):
            with self.subTest(value):
                self.assertIsNone(parse_retry_after(value, 30.0))
        self.assertEqual(parse_retry_after("Thu, 01 Jan 1970 00:00:00 GMT", 30.0), 0.0)

    def test_signed_retry_after_backs_off_with_jitter(self) -> None:
        headers = Message()
        headers["Retry-After"] = "+5"
        signed = HTTPError("https://workers.example.com", 503, "busy", headers, BytesIO(b"{}"))
        opener = FakeOpener([signed, {"items": []}])
        with patch("postgrip._internal.transport.jitter", return_value=0.125), \
             patch("postgrip._internal.transport.time.sleep") as sleep:
            self.assertEqual(client(opener, enable_retries=True).list(), {"items": []})
        sleep.assert_called_once_with(0.125)


if __name__ == "__main__":
    unittest.main()
