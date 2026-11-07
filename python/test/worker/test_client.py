from __future__ import annotations

import asyncio
from io import BytesIO
import json
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import build_opener
from unittest.mock import patch

from _http_fakes import FakeOpener, FakeResponse
from postgrip.worker import AsyncWorkerClient, WorkerAPIError, WorkerClient


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
    def test_create_sends_caller_owned_bootstrap_material_and_idempotency_key(self) -> None:
        opener = FakeOpener([{"worker": {}, "bootstrap": {}, "etag": "worker-etag", "receipt": {}}])
        client = WorkerClient(
            base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        response = client.create({
            "name": "worker",
            "host": "https://worker.example.com",
            "autoShutdownOnRemoval": True,
            "bootstrap": {
                "enrollmentKey": "enrollment-value",
                "attestationBootstrapToken": "attestation-value",
            },
        }, idempotency_key="worker-create-1")

        request = opener.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(urlparse(request.full_url).path, "/api/v1/workers")
        self.assertEqual(request.get_header("Authorization"), "Bearer pgt_test-token")
        self.assertEqual(request.get_header("Idempotency-key"), "worker-create-1")
        self.assertEqual(json.loads(request.data), {
            "name": "worker",
            "host": "https://worker.example.com",
            "autoShutdownOnRemoval": True,
            "bootstrap": {
                "enrollmentKey": "enrollment-value",
                "attestationBootstrapToken": "attestation-value",
            },
        })
        self.assertEqual(response["etag"], "worker-etag")

    def test_every_worker_facade_maps_to_the_canonical_operation(self) -> None:
        expected = [
            ("GET", "/health"),
            ("POST", "/api/v1/workers"),
            ("GET", "/api/v1/workers"),
            ("GET", "/api/v1/workers/worker-id"),
            ("GET", "/api/v1/workers/worker-id/assignments"),
            ("GET", "/api/v1/workers/worker-id/jobs"),
            ("GET", "/api/v1/workers/worker-id/jobs/job-id"),
            ("POST", "/api/v1/workers/worker-id/check"),
            ("POST", "/api/v1/workers/worker-id/maintenance"),
            ("POST", "/api/v1/workers/worker-id/maintenance/resume"),
            ("POST", "/api/v1/workers/worker-id/upgrade"),
            ("GET", "/api/v1/workers/worker-id/operational-logs"),
            ("GET", "/api/v1/workers/worker-id/security-logs"),
            ("GET", "/api/v1/workers/worker-id/snapshot/status"),
            ("GET", "/api/v1/workers/worker-id/snapshots"),
            ("POST", "/api/v1/workers/worker-id/snapshots"),
            ("GET", "/api/v1/workers/worker-id/snapshot/settings"),
            ("PUT", "/api/v1/workers/worker-id/snapshot/settings"),
            ("GET", "/api/v1/storage-destinations"),
            ("GET", "/api/v1/workers/worker-id/removal-impact"),
            ("DELETE", "/api/v1/workers/worker-id"),
        ]
        opener = FakeOpener([{} for _ in expected])
        client = WorkerClient(
            base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]

        calls = [
            client.health,
            lambda: client.create({
                "name": "worker",
                "host": "https://worker.example.com",
                "autoShutdownOnRemoval": True,
                "bootstrap": {
                    "enrollmentKey": "enrollment-value",
                    "attestationBootstrapToken": "attestation-value",
                },
            }, idempotency_key="operation-1"),
            lambda: client.list(status="ready", trust_state="trusted"),
            lambda: client.get("worker-id"),
            lambda: client.assignments("worker-id"),
            lambda: client.jobs("worker-id", page_size=10, state="running"),
            lambda: client.job("worker-id", "job-id"),
            lambda: client.check("worker-id", idempotency_key="operation-1"),
            lambda: client.maintenance("worker-id", idempotency_key="operation-1"),
            lambda: client.resume("worker-id", idempotency_key="operation-1"),
            lambda: client.upgrade("worker-id", idempotency_key="operation-1"),
            lambda: client.operational_logs("worker-id", service="worker", stream="stderr"),
            lambda: client.security_logs("worker-id", severity="warn", focus="upgrade"),
            lambda: client.snapshot_status("worker-id"),
            lambda: client.snapshots("worker-id"),
            lambda: client.take_snapshot("worker-id", idempotency_key="operation-1"),
            lambda: client.snapshot_settings("worker-id"),
            lambda: client.update_snapshot_settings("worker-id", {"enabled": False}, idempotency_key="operation-1"),
            client.storage_destinations,
            lambda: client.removal_impact("worker-id"),
            lambda: client.remove("worker-id", idempotency_key="operation-1", if_match='"impact-1"'),
        ]
        for invoke in calls:
            invoke()

        actual = [(request.method, urlparse(request.full_url).path) for request in opener.requests]
        self.assertEqual(actual, expected)
        self.assertIsNone(opener.requests[0].get_header("Authorization"))
        self.assertTrue(all(
            request.get_header("Authorization") == "Bearer pgt_test-token"
            for request in opener.requests[1:]
        ))
        self.assertTrue(all(
            request.get_header("Idempotency-key") == "operation-1"
            for request in [opener.requests[1], *opener.requests[7:11], opener.requests[15], opener.requests[17]]
        ))

    def test_worker_and_job_pages_preserve_opaque_tokens(self) -> None:
        opener = FakeOpener([
            {"items": [], "nextPageToken": "worker-next"},
            {"items": []},
            {"items": [], "nextPageToken": "job-next"},
            {"items": []},
        ])
        client = WorkerClient(
            base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]

        self.assertEqual([page.get("nextPageToken") for page in client.pages(page_size=1)], ["worker-next", None])
        self.assertEqual(
            [page.get("nextPageToken") for page in client.job_pages("worker-id", page_size=1)],
            ["job-next", None],
        )
        self.assertNotIn("pageToken=", opener.requests[0].full_url)
        self.assertIn("pageToken=worker-next", opener.requests[1].full_url)
        self.assertNotIn("pageToken=", opener.requests[2].full_url)
        self.assertIn("pageToken=job-next", opener.requests[3].full_url)

    def test_security_follower_deduplicates_entries_across_pages(self) -> None:
        opener = FakeOpener([
            {"items": [{"id": 7}, {"id": 8}], "nextCursor": "next"},
            {"items": [{"id": 8}, {"id": 9}], "nextCursor": "later"},
        ])
        client = WorkerClient(
            base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        cancel = Event()
        iterator = client.follow_security_logs("worker-id", cancel=cancel, severity="error")

        self.assertEqual([next(iterator)["id"] for _ in range(3)], [7, 8, 9])
        cancel.set()
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertIn("cursor=next", opener.requests[1].full_url)

    def test_list_injects_bearer_and_query(self) -> None:
        opener = FakeOpener([{"items": []}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        self.assertEqual(client.list(page_size=25), {"items": []})
        request = opener.requests[0]
        self.assertIn("pageSize=25", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer pgt_test-token")

    def test_list_exposes_observed_signer_runtime(self) -> None:
        opener = FakeOpener([{"items": [{
            "id": "worker-1",
            "name": "worker-east",
            "status": "online",
            "trustState": "trusted",
            "createdAt": "2026-08-25T00:00:00Z",
            "updatedAt": "2026-08-25T00:00:00Z",
            "capabilities": [],
            "previewSubdomainEnabled": False,
            "autoShutdownOnRemoval": False,
            "signerVersion": 2,
            "signerRevision": "30a3e4c53a48544f77735398f4784c20279f0ae3",
        }]}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]

        worker = client.list()["items"][0]
        self.assertEqual(worker["signerVersion"], 2)
        self.assertEqual(worker["signerRevision"], "30a3e4c53a48544f77735398f4784c20279f0ae3")

    def test_idempotent_mutation_retries_when_enabled(self) -> None:
        opener = FakeOpener([api_error(503), api_error(503), {
            "status": "queued", "worker": {}, "lifecycleDirective": "upgrade",
            "expectedVersion": 2, "workerImage": "image",
            "expectedSignerVersion": 3, "signerImage": "signer",
            "receipt": {"requestId": "req", "auditRecorded": True, "replayed": False},
        }])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                              opener=opener, enable_retries=True)  # type: ignore[arg-type]
        result = client.upgrade("worker", idempotency_key="upgrade-1")
        self.assertEqual(result["expectedVersion"], 2)
        self.assertEqual(result["expectedSignerVersion"], 3)
        self.assertEqual(result["signerImage"], "signer")
        self.assertEqual(len(opener.requests), 3)
        self.assertTrue(all(request.get_header("Idempotency-key") == "upgrade-1" for request in opener.requests))

    def test_typed_error_and_no_default_retry(self) -> None:
        opener = FakeOpener([api_error(503, "WORKER_UNAVAILABLE", "3")])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(WorkerAPIError) as raised:
            client.get("worker")
        self.assertEqual(raised.exception.code, "WORKER_UNAVAILABLE")
        self.assertEqual(raised.exception.request_id, "req-1")
        self.assertEqual(raised.exception.retry_after, 3)
        self.assertEqual(len(opener.requests), 1)

    def test_non_object_error_is_typed_and_retried(self) -> None:
        opener = FakeOpener([api_error_value(503, None), api_error_value(503, []), api_error_value(503, "busy")])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                              opener=opener, enable_retries=True)  # type: ignore[arg-type]
        with self.assertRaises(WorkerAPIError) as raised:
            client.get("worker")
        self.assertEqual(raised.exception.code, "HTTP_ERROR")
        self.assertEqual(raised.exception.request_id, "req-fallback")
        self.assertEqual(len(opener.requests), 3)

    def test_retry_after_only_controls_rate_limit_and_service_unavailable_backoff(self) -> None:
        opener = FakeOpener([api_error(502, retry_after="30"), {"items": []}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                              opener=opener, enable_retries=True)  # type: ignore[arg-type]

        with patch("postgrip._internal.transport.jitter", return_value=0.125), \
             patch("postgrip._internal.transport.time.sleep") as sleep:
            self.assertEqual(client.list(), {"items": []})

        sleep.assert_called_once_with(0.125)

    def test_security_log_query_uses_wire_names(self) -> None:
        opener = FakeOpener([{"items": [], "nextCursor": "cursor"}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                              opener=opener)  # type: ignore[arg-type]
        client.security_logs("worker", correlation_id="corr-1", since="2026-08-24T12:00:00Z")
        request = opener.requests[0]
        self.assertIn("correlationId=corr-1", request.full_url)
        self.assertNotIn("correlation_id", request.full_url)
        self.assertIn("since=2026-08-24T12%3A00%3A00Z", request.full_url)

    def test_requires_https_and_non_empty_opaque_worker_token(self) -> None:
        with self.assertRaises(ValueError):
            WorkerClient(base_url="http://example.com", token="pgt_token")
        with self.assertRaises(ValueError):
            WorkerClient(base_url="https://example.com", token="   ")
        self.assertIsInstance(
            WorkerClient(base_url="https://example.com", token="opaque-token"),
            WorkerClient,
        )

    def test_sync_and_async_clients_load_unified_environment_variables(self) -> None:
        environment = {
            "POSTGRIP_URL": "https://common.example.test",
            "POSTGRIP_WORKER_URL": "https://workers.example.test",
            "POSTGRIP_TOKEN": "pgt_environment",
        }
        self.assertIsInstance(WorkerClient.from_env(environ=environment), WorkerClient)
        self.assertIsInstance(AsyncWorkerClient.from_env(environ=environment), AsyncWorkerClient)

    def test_normalizes_base_url_and_blocks_redirects_on_injected_opener(self) -> None:
        opener = FakeOpener([{"items": []}])
        client = WorkerClient(base_url="  https://workers.example.com/base/  ", token="pgt_test-token",
                              opener=opener)  # type: ignore[arg-type]
        client.list()
        self.assertEqual(opener.requests[0].full_url, "https://workers.example.com/base/api/v1/workers")

        injected = build_opener()
        protected = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token", opener=injected)
        redirect_handlers = [handler for handler in protected._opener.handlers
                             if hasattr(handler, "http_error_302")]
        self.assertEqual(len(redirect_handlers), 1)
        self.assertEqual(type(redirect_handlers[0]).__name__, "_NoRedirect")

    def test_sync_follow_stops_before_buffered_entry_after_cancel(self) -> None:
        opener = FakeOpener([{"items": [{"id": 1}, {"id": 2}], "nextCursor": "cursor"}])
        client = WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                              opener=opener)  # type: ignore[arg-type]
        cancel = Event()
        iterator = client.follow_operational_logs("worker", cancel=cancel)
        self.assertEqual(next(iterator)["id"], 1)
        cancel.set()
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_sync_follow_cancellation_aborts_in_flight_request(self) -> None:
        request_started = Event()
        client_disconnected = Event()

        class BlockingHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                request_started.set()
                self.connection.settimeout(2)
                try:
                    if self.connection.recv(1) == b"":
                        client_disconnected.set()
                except OSError:
                    client_disconnected.set()

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingHandler)
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            client = WorkerClient(
                base_url=f"http://127.0.0.1:{server.server_port}",
                token="pgt_test-token",
                insecure_development=True,
                timeout=10,
            )
            cancel = Event()
            iterator = client.follow_operational_logs("worker", cancel=cancel)
            stopped = Event()
            errors: list[BaseException] = []

            def consume() -> None:
                try:
                    next(iterator)
                except StopIteration:
                    stopped.set()
                except BaseException as error:
                    errors.append(error)

            consumer = Thread(target=consume)
            consumer.start()
            self.assertTrue(request_started.wait(1), "log request did not reach the server")
            cancel.set()

            self.assertTrue(stopped.wait(1), "log follower did not stop after cancellation")
            self.assertTrue(client_disconnected.wait(1), "in-flight HTTP connection remained open")
            consumer.join(1)
            self.assertEqual(errors, [])
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(1)

    def test_async_follow_is_cancellable(self) -> None:
        async def run() -> None:
            opener = FakeOpener([{"items": [], "nextCursor": "cursor"}])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
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
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                                       opener=opener)  # type: ignore[arg-type]
            operational = await client.operational_logs("worker", since="2026-08-24T12:00:00Z")
            security = await client.security_logs("worker", correlation_id="corr-1")
            self.assertEqual(operational["nextCursor"], "operational")
            self.assertEqual(security["nextCursor"], "security")

        asyncio.run(run())

    def test_async_job_pages_follow_next_page_token(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [{"id": "job-1"}], "nextPageToken": "next"},
                {"items": [{"id": "job-2"}]},
            ])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                                       opener=opener)  # type: ignore[arg-type]
            pages = [page async for page in client.job_pages("worker", page_size=1)]

            self.assertEqual([page["items"][0]["id"] for page in pages], ["job-1", "job-2"])
            self.assertNotIn("pageToken", opener.requests[0].full_url)
            self.assertIn("pageToken=next", opener.requests[1].full_url)

        asyncio.run(run())

    def test_async_facades_and_worker_pages_execute_sync_transport(self) -> None:
        async def run() -> None:
            responses = [
                {},
                {"items": [], "nextPageToken": "next"},
                {"items": []},
                {}, {}, {}, {}, {}, {}, {}, {}, {}, {},
                {}, {}, {}, {}, {},
                {"items": []},
                {"etag": '"impact-1"'}, {"shutdownRequested": True},
            ]
            opener = FakeOpener(responses)
            client = AsyncWorkerClient(
                base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
            )  # type: ignore[arg-type]

            await client.health()
            self.assertEqual(
                [page.get("nextPageToken") async for page in client.pages(page_size=1)],
                ["next", None],
            )
            await client.get("worker-id")
            await client.assignments("worker-id")
            await client.jobs("worker-id", state="running")
            await client.job("worker-id", "job-id")
            await client.check("worker-id", idempotency_key="operation-1")
            await client.maintenance("worker-id", idempotency_key="operation-1")
            await client.resume("worker-id", idempotency_key="operation-1")
            await client.upgrade("worker-id", idempotency_key="operation-1")
            await client.operational_logs("worker-id")
            await client.security_logs("worker-id")
            await client.snapshot_status("worker-id")
            await client.snapshots("worker-id")
            await client.take_snapshot("worker-id", idempotency_key="operation-1")
            await client.snapshot_settings("worker-id")
            await client.update_snapshot_settings("worker-id", {"enabled": False}, idempotency_key="operation-1")
            self.assertEqual(await client.storage_destinations(), {"items": []})
            self.assertEqual(await client.removal_impact("worker-id"), {"etag": '"impact-1"'})
            self.assertEqual(
                await client.remove("worker-id", idempotency_key="operation-1", if_match='"impact-1"'),
                {"shutdownRequested": True},
            )
            self.assertEqual(opener.requests[-1].get_header("If-match"), '"impact-1"')

            self.assertEqual(len(opener.requests), 21)

        asyncio.run(run())

    def test_async_security_follower_deduplicates_entries(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [{"id": 1}, {"id": 2}], "nextCursor": "next"},
                {"items": [{"id": 2}, {"id": 3}], "nextCursor": "later"},
            ])
            client = AsyncWorkerClient(
                base_url="https://workers.example.com", token="pgt_test-token", opener=opener,
            )  # type: ignore[arg-type]
            iterator = client.follow_security_logs("worker-id")
            entries = [await anext(iterator) for _ in range(3)]
            await iterator.aclose()
            self.assertEqual([entry["id"] for entry in entries], [1, 2, 3])

        asyncio.run(run())

    def test_async_cancellation_stops_retry_backoff(self) -> None:
        async def run() -> None:
            opener = FakeOpener([api_error(503, retry_after="30"), {"items": []}])
            client = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
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
