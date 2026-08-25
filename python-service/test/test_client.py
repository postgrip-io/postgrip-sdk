from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import json
from threading import Event
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from postgrip_service import AsyncServiceClient, ServiceAPIError, ServiceClient, ServiceReference


SERVICE = {
    "ref": "project:11111111-1111-4111-8111-111111111111",
    "id": "11111111-1111-4111-8111-111111111111",
    "source": "project",
    "facets": [],
    "name": "api",
    "slug": "api",
    "kind": "backend",
    "mode": "deployed",
    "status": "ready",
    "workers": [],
    "environmentCount": 1,
    "capabilities": [],
    "createdAt": "2026-08-24T00:00:00Z",
    "updatedAt": "2026-08-24T00:00:00Z",
}


class FakeResponse:
    def __init__(self, value: object):
        self.body = json.dumps(value).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.body[:limit]


class FakeOpener:
    def __init__(self, responses: list[object]):
        self.responses = responses
        self.requests = []
        self.handlers = []

    def add_handler(self, handler: object) -> None:
        self.handlers.append(handler)

    def open(self, request: object, timeout: float = 0) -> FakeResponse:
        self.requests.append(request)
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)


def api_error(status: int, code: str = "BUSY", retry_after: str = "0") -> HTTPError:
    headers = Message()
    headers["Retry-After"] = retry_after
    body = BytesIO(json.dumps({"code": code, "message": "try later", "requestId": "req-1"}).encode())
    return HTTPError("https://services.example.test", status, "failed", headers, body)


class ServiceClientTests(unittest.TestCase):
    def test_list_injects_bearer_and_terminal_query_names(self) -> None:
        opener = FakeOpener([{"items": [SERVICE], "nextCursor": ""}])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        page = client.list(kind="backend", worker_id="worker-id", limit=25)
        self.assertEqual(page["items"][0]["name"], "api")
        request = opener.requests[0]
        self.assertIn("kind=backend", request.full_url)
        self.assertIn("worker=worker-id", request.full_url)
        self.assertNotIn("worker_id", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer pgwm_test-token")

    def test_resolve_and_scoped_status(self) -> None:
        opener = FakeOpener([SERVICE, {"service": SERVICE, "environments": []}])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        service = client.resolve("api")
        status = client.for_service(service).status()
        self.assertEqual(status["service"]["ref"], SERVICE["ref"])
        self.assertIn(f"/api/v1/services/project/{SERVICE['id']}/status", opener.requests[1].full_url)

    def test_deploy_sends_json_and_idempotency_key(self) -> None:
        response = {
            "status": "queued", "serviceRef": SERVICE["ref"], "environmentId": "environment-id",
            "deploymentId": "deployment-id", "deployment": {},
            "receipt": {"requestId": "request-id", "auditRecorded": True, "replayed": False},
        }
        opener = FakeOpener([response])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        result = client.deploy(
            str(SERVICE["id"]), environment_id="environment-id", branch="main",
            expected_commit_sha="abc123", idempotency_key="deploy-1",
        )
        self.assertEqual(result["deploymentId"], "deployment-id")
        request = opener.requests[0]
        self.assertEqual(request.get_header("Idempotency-key"), "deploy-1")
        self.assertEqual(json.loads(request.data), {
            "environmentId": "environment-id", "branch": "main", "expectedCommitSha": "abc123",
        })

    def test_idempotent_mutation_retries_when_enabled(self) -> None:
        response = {
            "status": "cancelled", "serviceRef": SERVICE["ref"], "environmentId": "environment-id",
            "deploymentId": "deployment-id", "deployment": {},
            "receipt": {"requestId": "request-id", "auditRecorded": True, "replayed": False},
        }
        opener = FakeOpener([api_error(503), api_error(503), response])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token",
            opener=opener, enable_retries=True,
        )  # type: ignore[arg-type]
        with patch("postgrip_service.client.time.sleep"):
            self.assertEqual(client.cancel("project", "deployment", idempotency_key="cancel-1")["status"], "cancelled")
        self.assertEqual(len(opener.requests), 3)

    def test_invalid_idempotency_key_fails_before_request(self) -> None:
        opener = FakeOpener([])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            client.cancel("project", "deployment", idempotency_key="contains space")
        self.assertEqual(opener.requests, [])

    def test_pages_use_opaque_cursor(self) -> None:
        opener = FakeOpener([
            {"items": [], "nextCursor": "next"},
            {"items": [], "nextCursor": ""},
        ])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        self.assertEqual([page["nextCursor"] for page in client.pages()], ["next", ""])
        self.assertNotIn("cursor=", opener.requests[0].full_url)
        self.assertIn("cursor=next", opener.requests[1].full_url)

    def test_follow_uses_cursor_and_stops_after_cancel(self) -> None:
        opener = FakeOpener([
            {"items": [{"kind": "runtime", "message": "one"}, {"kind": "runtime", "message": "two"}], "nextCursor": "next", "pollAfterMs": 1},
        ])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        cancel = Event()
        iterator = client.follow_logs(ServiceReference("project", "project-id"), cancel=cancel)
        self.assertEqual(next(iterator)["message"], "one")
        cancel.set()
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertIn("follow=True", opener.requests[0].full_url)

    def test_follow_honors_positive_server_poll_delay(self) -> None:
        opener = FakeOpener([
            {"items": [], "nextCursor": "next", "pollAfterMs": 25},
        ])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token",
            opener=opener, follow_interval=2.0,
        )  # type: ignore[arg-type]
        cancel = Event()

        def stop_after_delay(delay: float) -> bool:
            self.assertEqual(delay, 0.025)
            cancel.set()
            return True

        iterator = client.follow_logs(ServiceReference("project", "project-id"), cancel=cancel)
        with patch.object(cancel, "wait", side_effect=stop_after_delay):
            with self.assertRaises(StopIteration):
                next(iterator)

    def test_typed_error_does_not_leak_body(self) -> None:
        headers = Message()
        headers["X-Request-ID"] = "request-header"
        error = HTTPError(
            "https://services.example.test", 502, "failed", headers, BytesIO(b"secret upstream body"),
        )
        opener = FakeOpener([error])
        client = ServiceClient(base_url="https://services.example.test", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(ServiceAPIError) as raised:
            client.resolve("api")
        self.assertEqual(raised.exception.code, "HTTP_ERROR")
        self.assertEqual(raised.exception.request_id, "request-header")
        self.assertNotIn("secret", str(raised.exception))

    def test_requires_https_and_management_token(self) -> None:
        with self.assertRaises(ValueError):
            ServiceClient(base_url="http://example.test", token="pgwm_token")
        with self.assertRaises(ValueError):
            ServiceClient(base_url="https://example.test", token="pga_token")

    def test_async_pages(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [], "nextCursor": "next"},
                {"items": [], "nextCursor": ""},
            ])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgwm_test-token", opener=opener,
            )  # type: ignore[arg-type]
            cursors = [page["nextCursor"] async for page in client.pages()]
            self.assertEqual(cursors, ["next", ""])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
