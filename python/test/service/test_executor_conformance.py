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
from postgrip._internal.transport import PostGripAPIError
from postgrip.service import ServiceAPIError, ServiceClient
from postgrip.service.openapi import OperationId

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "service-openapi.json"


def contract_operations() -> list[dict[str, object]]:
    """Every Service operation with the annotations the executor must follow, read from the contract."""
    spec = json.loads(CONTRACT.read_text())

    def resolve(parameter: dict[str, object]) -> dict[str, object]:
        reference = parameter.get("$ref")
        if isinstance(reference, str):
            return spec["components"]["parameters"][reference.rsplit("/", 1)[-1]]
        return parameter

    operations = []
    for path, item in spec["paths"].items():
        shared = item.get("parameters", [])
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            parameters = [resolve(parameter) for parameter in [*shared, *operation.get("parameters", [])]]
            operations.append({
                "id": OperationId(operation["operationId"]),
                "method": method.upper(),
                "path": path,
                "safety": operation["x-postgrip-safety"],
                "idempotency": operation["x-postgrip-idempotency"],
                "retry": operation["x-postgrip-retry"],
                "headers": {parameter["name"] for parameter in parameters if parameter.get("in") == "header"},
                "has_body": "requestBody" in operation,
            })
    return operations


def busy() -> HTTPError:
    headers = Message()
    headers["Retry-After"] = "0"
    body = BytesIO(json.dumps({"code": "BUSY", "message": "busy", "requestId": "req-1"}).encode())
    return HTTPError("https://services.example.com", 503, "Service Unavailable", headers, body)


def call(client: ServiceClient, operation: dict[str, object], headers: dict[str, str]) -> object:
    path = str(operation["path"])
    return client.openapi.request(
        operation["id"],  # type: ignore[arg-type]
        {} if operation["has_body"] else None,
        path_parameters={name: f"p-{name}" for name in re.findall(r"\{(\w+)\}", path)},
        headers=headers or None,
    )


def client(opener: FakeOpener, *, enable_retries: bool = False) -> ServiceClient:
    return ServiceClient(base_url="https://services.example.com", token="pgt_management",
                         opener=opener, enable_retries=enable_retries)  # type: ignore[arg-type]


class ServiceExecutorConformanceTests(unittest.TestCase):
    def test_covers_every_generated_service_operation(self) -> None:
        self.assertEqual(len(contract_operations()), 119)

    def test_each_operation_follows_its_contract_annotations(self) -> None:
        for operation in contract_operations():
            key = "key-1" if operation["idempotency"] == "required" else None
            declared = operation["headers"]
            # If-Match is offered on every operation; only those declaring it may forward it.
            sent = {**({"Idempotency-Key": key} if key else {}), "If-Match": '"etag-1"'}
            eligible = operation["retry"] == "bounded" and (operation["safety"] == "read-only" or key is not None)
            with self.subTest(operation["id"].value):  # type: ignore[union-attr]
                opener = FakeOpener([{}])
                call(client(opener), operation, sent)
                request = opener.requests[0]
                self.assertEqual(request.get_method(), operation["method"])
                self.assertEqual(request.get_header("Authorization"), "Bearer pgt_management")
                self.assertEqual(request.get_header("Idempotency-key"),
                                 key if key and "Idempotency-Key" in declared else None)  # type: ignore[operator]
                self.assertEqual(request.get_header("If-match"),
                                 '"etag-1"' if "If-Match" in declared else None)  # type: ignore[operator]
                self.assertEqual(request.get_header("Content-type"),
                                 "application/json" if operation["has_body"] else None)

                with patch("postgrip._internal.transport.time.sleep"):
                    retrying = FakeOpener([busy(), {}])
                    if eligible:
                        self.assertEqual(call(client(retrying, enable_retries=True), operation, sent), {})
                        self.assertEqual(len(retrying.requests), 2)
                        self.assertEqual(len({r.get_header("Idempotency-key") for r in retrying.requests}), 1)
                    else:
                        with self.assertRaises(ServiceAPIError):
                            call(client(retrying, enable_retries=True), operation, sent)
                        self.assertEqual(len(retrying.requests), 1)

                    disabled = FakeOpener([busy(), {}])
                    with self.assertRaises(ServiceAPIError):
                        call(client(disabled), operation, sent)
                    self.assertEqual(len(disabled.requests), 1)

                if key:
                    missing = FakeOpener([{}])
                    with self.assertRaisesRegex(ValueError, "visible ASCII"):
                        call(client(missing), operation, {})
                    self.assertEqual(missing.requests, [])

    def test_error_keeps_its_fields_and_text_and_is_a_postgrip_api_error(self) -> None:
        headers = Message()
        headers["X-Request-ID"] = "req-header"
        body = BytesIO(json.dumps({"code": "NOT_FOUND", "message": "service not found", "details": {"id": "s"}}).encode())
        opener = FakeOpener([HTTPError("https://services.example.com", 404, "Not Found", headers, body)])
        with self.assertRaises(ServiceAPIError) as raised:
            client(opener).resolve("api")
        error = raised.exception
        self.assertIsInstance(error, PostGripAPIError)
        self.assertEqual((error.status, error.code, error.message, error.request_id, error.details),
                         (404, "NOT_FOUND", "service not found", "req-header", {"id": "s"}))
        self.assertEqual(str(error), "postgrip-service: NOT_FOUND (HTTP 404): service not found")

    def test_screenshot_bound_applies_to_success_bodies_only(self) -> None:
        data = "A" * ((4 << 20) + 4)
        success = FakeOpener([{"contentType": "image/png", "dataBase64": data}])
        screenshot = client(success).administration.diagnostics.get_service_deployment_screenshot("project-id", "deployment-id")
        self.assertEqual(len(screenshot["dataBase64"]), len(data))

        body = BytesIO(json.dumps({"code": "FAILED", "message": data}).encode())
        failure = FakeOpener([HTTPError("https://services.example.com", 500, "Internal Server Error", Message(), body)])
        with self.assertRaises(ServiceAPIError) as raised:
            client(failure).administration.diagnostics.get_service_deployment_screenshot("project-id", "deployment-id")
        self.assertEqual(raised.exception.code, "HTTP_ERROR")

    def test_signed_or_fractional_retry_after_backs_off_with_jitter(self) -> None:
        for value in ("+5", "1.5"):
            with self.subTest(value):
                headers = Message()
                headers["Retry-After"] = value
                signed = HTTPError("https://services.example.com", 503, "busy", headers, BytesIO(b"{}"))
                opener = FakeOpener([signed, {"id": "api"}])
                with patch("postgrip._internal.transport.jitter", return_value=0.125), \
                     patch("postgrip._internal.transport.time.sleep") as sleep:
                    client(opener, enable_retries=True).resolve("api")
                sleep.assert_called_once_with(0.125)


if __name__ == "__main__":
    unittest.main()
