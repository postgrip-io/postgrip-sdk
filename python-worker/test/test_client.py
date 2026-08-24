from __future__ import annotations

import asyncio
from io import BytesIO
import json
from email.message import Message
from threading import Event
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener

from postgrip_worker import AsyncWorkerClient, WorkerAPIError, WorkerClient


class FakeResponse:
    def __init__(self, value: object):
        self.body = json.dumps(value).encode()

    def __enter__(self) -> "FakeResponse":
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
    return HTTPError("https://workers.example.com", status, "failed", headers, body)


def api_error_value(status: int, value: object, retry_after: str = "0") -> HTTPError:
    headers = Message()
    headers["Retry-After"] = retry_after
    headers["X-Request-ID"] = "req-fallback"
    return HTTPError("https://workers.example.com", status, "failed", headers, BytesIO(json.dumps(value).encode()))


class WorkerClientTests(unittest.TestCase):
    def test_list_injects_bearer_and_query(self) -> None:
        opener = FakeOpener([{"items": []}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        self.assertEqual(client.list(page_size=25), {"items": []})
        request = opener.requests[0]
        self.assertIn("pageSize=25", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer pgwm_test-token")

    def test_idempotent_mutation_retries_when_enabled(self) -> None:
        opener = FakeOpener([api_error(503), api_error(503), {
            "status": "queued", "worker": {}, "lifecycleDirective": "upgrade",
            "expectedVersion": 2, "workerImage": "image",
            "receipt": {"requestId": "req", "auditRecorded": True, "replayed": False},
        }])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                              opener=opener, enable_retries=True)  # type: ignore[arg-type]
        self.assertEqual(client.upgrade("worker", idempotency_key="upgrade-1")["expectedVersion"], 2)
        self.assertEqual(len(opener.requests), 3)
        self.assertTrue(all(request.get_header("Idempotency-key") == "upgrade-1" for request in opener.requests))

    def test_typed_error_and_no_default_retry(self) -> None:
        opener = FakeOpener([api_error(503, "WORKER_UNAVAILABLE", "3")])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(WorkerAPIError) as raised:
            client.get("worker")
        self.assertEqual(raised.exception.code, "WORKER_UNAVAILABLE")
        self.assertEqual(raised.exception.request_id, "req-1")
        self.assertEqual(raised.exception.retry_after, 3)
        self.assertEqual(len(opener.requests), 1)

    def test_non_object_error_is_typed_and_retried(self) -> None:
        opener = FakeOpener([api_error_value(503, None), api_error_value(503, []), api_error_value(503, "busy")])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                              opener=opener, enable_retries=True)  # type: ignore[arg-type]
        with self.assertRaises(WorkerAPIError) as raised:
            client.get("worker")
        self.assertEqual(raised.exception.code, "HTTP_ERROR")
        self.assertEqual(raised.exception.request_id, "req-fallback")
        self.assertEqual(len(opener.requests), 3)

    def test_security_log_query_uses_wire_names(self) -> None:
        opener = FakeOpener([{"items": [], "nextCursor": "cursor"}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                              opener=opener)  # type: ignore[arg-type]
        client.security_logs("worker", correlation_id="corr-1", since="2026-08-24T12:00:00Z")
        request = opener.requests[0]
        self.assertIn("correlationId=corr-1", request.full_url)
        self.assertNotIn("correlation_id", request.full_url)
        self.assertIn("since=2026-08-24T12%3A00%3A00Z", request.full_url)

    def test_requires_https_and_worker_token(self) -> None:
        with self.assertRaises(ValueError):
            WorkerClient(base_url="http://example.com", token="pgwm_token")
        with self.assertRaises(ValueError):
            WorkerClient(base_url="https://example.com", token="pga_token")

    def test_normalizes_base_url_and_blocks_redirects_on_injected_opener(self) -> None:
        opener = FakeOpener([{"items": []}])
        client = WorkerClient(base_url="  https://workers.example.com/base/  ", token="pgwm_test-token",
                              opener=opener)  # type: ignore[arg-type]
        client.list()
        self.assertEqual(opener.requests[0].full_url, "https://workers.example.com/base/api/v1/workers")

        injected = build_opener()
        protected = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token", opener=injected)
        redirect_handlers = [handler for handler in protected._opener.handlers
                             if hasattr(handler, "http_error_302")]
        self.assertEqual(len(redirect_handlers), 1)
        self.assertEqual(type(redirect_handlers[0]).__name__, "_NoRedirect")

    def test_sync_follow_stops_before_buffered_entry_after_cancel(self) -> None:
        opener = FakeOpener([{"items": [{"id": 1}, {"id": 2}], "nextCursor": "cursor"}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                              opener=opener)  # type: ignore[arg-type]
        cancel = Event()
        iterator = client.follow_operational_logs("worker", cancel=cancel)
        self.assertEqual(next(iterator)["id"], 1)
        cancel.set()
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_async_follow_is_cancellable(self) -> None:
        async def run() -> None:
            opener = FakeOpener([{"items": [], "nextCursor": "cursor"}])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                                       opener=opener, follow_interval=10)  # type: ignore[arg-type]
            iterator = client.follow_operational_logs("worker")
            task = asyncio.create_task(anext(iterator))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(run())

    def test_async_log_page_methods(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [], "nextCursor": "operational"},
                {"items": [], "nextCursor": "security"},
            ])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                                       opener=opener)  # type: ignore[arg-type]
            operational = await client.operational_logs("worker", since="2026-08-24T12:00:00Z")
            security = await client.security_logs("worker", correlation_id="corr-1")
            self.assertEqual(operational["nextCursor"], "operational")
            self.assertEqual(security["nextCursor"], "security")

        asyncio.run(run())

    def test_async_cancellation_stops_retry_backoff(self) -> None:
        async def run() -> None:
            opener = FakeOpener([api_error(503, retry_after="30"), {"items": []}])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgwm_test-token",
                                       opener=opener, enable_retries=True)  # type: ignore[arg-type]
            task = asyncio.create_task(client.list())
            while not opener.requests:
                await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)
            self.assertEqual(len(opener.requests), 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
