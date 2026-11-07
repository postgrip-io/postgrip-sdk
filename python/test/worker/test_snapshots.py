from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse
from unittest.mock import patch

from _http_fakes import FakeOpener, FakeResponse
from postgrip.worker import AsyncWorkerClient, WorkerAPIError, WorkerClient
from postgrip.worker import client as worker_client

SNAPSHOT_RUN = {
    "snapshot": {"workerId": "w", "snapshotId": "20261107T101500.000Z", "size": 1, "degraded": False, "skipped": []},
    "receipt": {"requestId": "req", "auditRecorded": True, "replayed": False},
}


def refusal(status: int, code: str, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    body = BytesIO(json.dumps({"code": code, "message": "refused", "requestId": "req"}).encode())
    return HTTPError("https://workers.example.com", status, "refused", headers, body)


class TimeoutRecordingOpener(FakeOpener):
    def __init__(self, responses: list[object]):
        super().__init__(responses)
        self.timeouts: list[float] = []

    def open(self, request: object, timeout: float = 0) -> FakeResponse:
        self.timeouts.append(timeout)
        return super().open(request, timeout)


def client(opener: FakeOpener, **options: Any) -> WorkerClient:
    return WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                        opener=opener, **options)  # type: ignore[arg-type]


class WorkerSnapshotTests(unittest.TestCase):
    def test_mutations_refuse_a_missing_or_invalid_key_before_sending(self) -> None:
        opener = FakeOpener([])
        worker = client(opener, enable_retries=True)
        for key in ("", "has space", "k" * 129):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    worker.take_snapshot("w", idempotency_key=key)
                with self.assertRaises(ValueError):
                    worker.update_snapshot_settings("w", {"enabled": False}, idempotency_key=key)
                with self.assertRaises(ValueError):
                    worker.openapi.create_worker_snapshot("w", idempotency_key=key)
                with self.assertRaises(ValueError):
                    worker.openapi.update_worker_snapshot_settings("w", {"enabled": False}, idempotency_key=key)
        self.assertEqual(opener.requests, [])

    def test_take_snapshot_sends_the_key_and_decodes_the_run(self) -> None:
        opener = FakeOpener([SNAPSHOT_RUN])
        self.assertEqual(client(opener).take_snapshot("w", idempotency_key="snapshot-1"), SNAPSHOT_RUN)
        request = opener.requests[0]
        self.assertEqual((request.method, urlparse(request.full_url).path), ("POST", "/api/v1/workers/w/snapshots"))
        self.assertEqual(request.get_header("Idempotency-key"), "snapshot-1")

    def test_take_snapshot_never_retries_unkept_answers_through_either_surface(self) -> None:
        for status, code in ((504, "SNAPSHOT_UNCONFIRMED"), (502, "SNAPSHOT_FAILED")):
            with self.subTest(code=code):
                opener = FakeOpener([refusal(status, code), refusal(status, code), SNAPSHOT_RUN])
                worker = client(opener, enable_retries=True)
                with patch("postgrip._internal.transport.time.sleep"):
                    with self.assertRaises(WorkerAPIError) as raised:
                        worker.take_snapshot("w", idempotency_key="snapshot-1")
                    self.assertEqual((raised.exception.status, raised.exception.code), (status, code))
                    self.assertEqual(len(opener.requests), 1)
                    with self.assertRaises(WorkerAPIError):
                        worker.openapi.create_worker_snapshot("w", idempotency_key="snapshot-1")
                    self.assertEqual(len(opener.requests), 2)

    def test_snapshot_reads_keep_the_bounded_retry_of_a_504(self) -> None:
        opener = FakeOpener([refusal(504, "GATEWAY_TIMEOUT"), {"workerId": "w"}])
        with patch("postgrip._internal.transport.time.sleep"):
            self.assertEqual(client(opener, enable_retries=True).snapshot_status("w"), {"workerId": "w"})
        self.assertEqual(len(opener.requests), 2)

    def test_take_snapshot_still_retries_a_rate_limit_with_the_same_key(self) -> None:
        opener = FakeOpener([refusal(429, "RATE_LIMITED", "0"), SNAPSHOT_RUN])
        with patch("postgrip._internal.transport.time.sleep"):
            self.assertEqual(client(opener, enable_retries=True).take_snapshot("w", idempotency_key="snapshot-1"), SNAPSHOT_RUN)
        self.assertEqual([r.get_header("Idempotency-key") for r in opener.requests], ["snapshot-1", "snapshot-1"])

    def test_in_progress_exposes_retry_after_without_retrying(self) -> None:
        opener = FakeOpener([refusal(409, "SNAPSHOT_IN_PROGRESS", "30"), SNAPSHOT_RUN])
        with self.assertRaises(WorkerAPIError) as raised:
            client(opener, enable_retries=True).take_snapshot("w", idempotency_key="snapshot-1")
        self.assertEqual((raised.exception.status, raised.exception.code), (409, "SNAPSHOT_IN_PROGRESS"))
        self.assertEqual(raised.exception.retry_after, 30)
        self.assertEqual(len(opener.requests), 1)

    def test_take_snapshot_outlives_the_server_wait_and_other_calls_keep_their_timeout(self) -> None:
        self.assertGreater(worker_client.SNAPSHOT_RUN_TIMEOUT, 300)
        opener = TimeoutRecordingOpener([SNAPSHOT_RUN, SNAPSHOT_RUN, {}])
        worker = client(opener)
        worker.take_snapshot("w", idempotency_key="snapshot-1")
        worker.openapi.create_worker_snapshot("w", idempotency_key="snapshot-1")
        worker.snapshot_status("w")
        self.assertEqual(opener.timeouts, [worker_client.SNAPSHOT_RUN_TIMEOUT, worker_client.SNAPSHOT_RUN_TIMEOUT, 30.0])
        longer = TimeoutRecordingOpener([SNAPSHOT_RUN])
        client(longer, timeout=900.0).take_snapshot("w", idempotency_key="snapshot-2")
        self.assertEqual(longer.timeouts, [900.0])

    def test_signing_key_is_write_only(self) -> None:
        settings = {"workerId": "w", "enabled": True, "volumesEnabled": False, "volumesHot": False, "hasSigningKey": True}
        receipt = {"requestId": "req", "auditRecorded": True, "replayed": False}
        opener = FakeOpener([{"settings": settings, "receipt": receipt}, {"settings": settings, "receipt": receipt}])
        worker = client(opener)
        saved = worker.update_snapshot_settings("w", {"enabled": True, "signingKey": "base64-seed"}, idempotency_key="settings-1")
        self.assertTrue(saved["settings"]["hasSigningKey"])
        worker.update_snapshot_settings("w", {"enabled": False}, idempotency_key="settings-1")
        request = opener.requests[0]
        self.assertEqual((request.method, urlparse(request.full_url).path), ("PUT", "/api/v1/workers/w/snapshot/settings"))
        self.assertEqual(request.get_header("Idempotency-key"), "settings-1")
        self.assertEqual(json.loads(opener.requests[0].data), {"enabled": True, "signingKey": "base64-seed"})
        self.assertEqual(json.loads(opener.requests[1].data), {"enabled": False})

    def test_no_snapshot_answer_type_declares_the_signing_key(self) -> None:
        source = Path(worker_client.__file__).with_name("openapi.py").read_text(encoding="utf-8")
        classes = dict(re.findall(r"^class (_Schema\w+)\(.*?\):\n((?:    .*\n)+)", source, re.MULTILINE))
        carriers = sorted(name for name, body in classes.items() if re.search(r"^\s+signingKey:", body, re.MULTILINE))
        self.assertEqual(carriers, ["_SchemaUpdateWorkerSnapshotSettingsRequestOptional"])
        aliases = dict(re.findall(r"^(\w+ResponseBody): TypeAlias = (\w+)$", source, re.MULTILINE))
        for body in ("CreateWorkerSnapshotResponseBody", "GetWorkerSnapshotSettingsResponseBody",
                     "GetWorkerSnapshotStatusResponseBody", "ListWorkerSnapshotsResponseBody",
                     "UpdateWorkerSnapshotSettingsResponseBody"):
            seen: set[str] = set()
            pending = [aliases[body]]
            while pending:
                name = pending.pop()
                if name in seen or name not in classes:
                    continue
                seen.add(name)
                header = re.search(rf"^class {name}\((\w+)\)", source, re.MULTILINE)
                pending.extend(re.findall(r"_Schema\w+", classes[name]))
                if header:
                    pending.append(header.group(1))
            self.assertTrue(seen, body)
            self.assertFalse(any(name.startswith("_SchemaUpdateWorkerSnapshotSettingsRequest") for name in seen), body)

    def test_async_snapshot_methods_share_the_sync_policy(self) -> None:
        async def run() -> None:
            opener = TimeoutRecordingOpener([{}, {"items": []}, refusal(504, "SNAPSHOT_UNCONFIRMED"), {}, {}])
            worker = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                                       opener=opener, enable_retries=True)  # type: ignore[arg-type]
            await worker.snapshot_status("w")
            await worker.snapshots("w")
            with self.assertRaises(WorkerAPIError):
                await worker.take_snapshot("w", idempotency_key="snapshot-1")
            await worker.snapshot_settings("w")
            await worker.update_snapshot_settings("w", {"enabled": False}, idempotency_key="settings-1")
            self.assertEqual(len(opener.requests), 5)
            self.assertEqual(opener.timeouts[2], worker_client.SNAPSHOT_RUN_TIMEOUT)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
