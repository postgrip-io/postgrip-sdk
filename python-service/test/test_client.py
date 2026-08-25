from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import json
from threading import Event
import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request
from unittest.mock import patch

from postgrip_service import AsyncServiceClient, ServiceAPIError, ServiceClient, ServiceReference
from postgrip_service.client import _NoRedirect


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
        self.body = value if isinstance(value, bytes) else json.dumps(value).encode()

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
        self.assertIn("follow=true", opener.requests[0].full_url)

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
        for base_url in ("https://example.test?", "https://example.test#"):
            with self.assertRaises(ValueError):
                ServiceClient(base_url=base_url, token="pgwm_token")
        with self.assertRaises(ValueError):
            ServiceClient(base_url="https://example.test", token="pgwm_token", retry_max_attempts=4)

    def test_loads_documented_service_environment_variables(self) -> None:
        client = ServiceClient.from_env(environ={
            "POSTGRIP_WORKERORCHESTRATOR_URL": "https://services.example.test",
            "POSTGRIP_SERVICE_API_TOKEN": "pgwm_environment-token",
        })
        self.assertIsInstance(client, ServiceClient)

    def test_retries_are_disabled_by_default(self) -> None:
        opener = FakeOpener([api_error(503)])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaises(ServiceAPIError):
            client.resolve("api")
        self.assertEqual(len(opener.requests), 1)

    def test_retry_configuration_caps_attempts_and_retry_after(self) -> None:
        opener = FakeOpener([api_error(503, retry_after="30"), api_error(503, retry_after="30")])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token", opener=opener,
            enable_retries=True, retry_max_attempts=2, retry_after_max_delay=0.001,
        )  # type: ignore[arg-type]
        with patch("postgrip_service.client.time.sleep") as sleep:
            with self.assertRaises(ServiceAPIError) as raised:
                client.resolve("api")
        sleep.assert_called_once_with(0.001)
        self.assertEqual(raised.exception.retry_after, 0.001)
        self.assertEqual(len(opener.requests), 2)

    def test_response_body_limit(self) -> None:
        opener = FakeOpener([b"x" * ((4 << 20) + 1)])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "too large"):
            client.resolve("api")

    def test_redirect_handler_never_constructs_a_forwarded_request(self) -> None:
        request = Request("https://services.example.test/api/v1/services", headers={
            "Authorization": "Bearer pgwm_test-token",
        })
        self.assertIsNone(_NoRedirect().redirect_request(
            request, None, 307, "redirect", Message(), "https://other.example.test/",
        ))

    def test_every_service_facade_maps_to_canonical_operation(self) -> None:
        expected = [
            ("GET", "/api/v1/services"),
            ("GET", "/api/v1/services/resolve"),
            ("GET", "/api/v1/services/project/service-id"),
            ("GET", "/api/v1/services/project/service-id/status"),
            ("GET", "/api/v1/services/project/service-id/environments"),
            ("GET", "/api/v1/services/project/service-id/environments/resolve"),
            ("GET", "/api/v1/services/project/service-id/deployments"),
            ("GET", "/api/v1/services/project/service-id/deployments/deployment-id"),
            ("GET", "/api/v1/services/project/service-id/logs"),
            ("POST", "/api/v1/services/project/service-id/check"),
            ("GET", "/api/v1/services/project/service-id/deploy/preview"),
            ("POST", "/api/v1/services/project/service-id/deploy"),
            ("POST", "/api/v1/services/project/service-id/redeploy"),
            ("POST", "/api/v1/services/project/service-id/deployments/deployment-id/cancel"),
            ("POST", "/api/v1/services/project/service-id/deployments/deployment-id/rollback"),
            ("POST", "/api/v1/services/project/service-id/environments/environment-id/start"),
            ("POST", "/api/v1/services/project/service-id/environments/environment-id/stop"),
            ("POST", "/api/v1/services/project/service-id/environments/environment-id/restart"),
        ]
        opener = FakeOpener([{} for _ in expected])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgwm_test-token", opener=opener,
        )  # type: ignore[arg-type]
        reference = ServiceReference("project", "service-id")
        calls = [
            lambda: client.list(),
            lambda: client.resolve("api"),
            lambda: client.get(reference),
            lambda: client.status(reference),
            lambda: client.environments(reference),
            lambda: client.environment("service-id", "production"),
            lambda: client.deployments(reference),
            lambda: client.deployment("service-id", "deployment-id"),
            lambda: client.logs(reference),
            lambda: client.check(reference, idempotency_key="key"),
            lambda: client.preview_deploy("service-id"),
            lambda: client.deploy("service-id", expected_commit_sha="sha", idempotency_key="key"),
            lambda: client.redeploy("service-id", idempotency_key="key"),
            lambda: client.cancel("service-id", "deployment-id", idempotency_key="key"),
            lambda: client.rollback("service-id", "deployment-id", idempotency_key="key"),
            lambda: client.start(
                "service-id", "environment-id", expected_deployment_id="deployment-id", idempotency_key="key",
            ),
            lambda: client.stop(
                "service-id", "environment-id", expected_deployment_id="deployment-id", idempotency_key="key",
            ),
            lambda: client.restart(
                "service-id", "environment-id", expected_deployment_id="deployment-id", idempotency_key="key",
            ),
        ]
        for invoke in calls:
            invoke()
        actual = [(request.method, urlparse(request.full_url).path) for request in opener.requests]
        self.assertEqual(actual, expected)

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

    def test_async_cancellation_interrupts_retry_backoff(self) -> None:
        async def run() -> None:
            opener = FakeOpener([api_error(503, retry_after="30")])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgwm_test-token",
                opener=opener, enable_retries=True,
            )  # type: ignore[arg-type]
            task = asyncio.create_task(client.resolve("api"))
            while not opener.requests:
                await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
