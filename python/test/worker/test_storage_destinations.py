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

from _http_fakes import FakeOpener
from postgrip.worker import AsyncWorkerClient, WorkerClient
from postgrip.worker import client as worker_client

DESTINATIONS = {
    "items": [
        {
            "id": "0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a",
            "name": "Production backups",
            "provider": "r2",
            "bucket": "pg-backups",
            "endpoint": "https://account.r2.cloudflarestorage.com",
            "accountId": "account",
            "prefix": "postgrip",
            "createdAt": "2026-11-01T09:30:00Z",
            "updatedAt": "2026-11-01T09:30:00Z",
        },
        {
            "id": "7e3f9a1b-2c4d-4e5f-8a6b-9c0d1e2f3a4b",
            "name": "us-east archive",
            "provider": "s3",
            "bucket": "acme-worker-snapshots",
            "region": "us-east-1",
            "createdAt": "2026-10-20T14:05:12Z",
            "updatedAt": "2026-11-03T08:00:00Z",
        },
    ],
}


def refusal(status: int, code: str, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    body = BytesIO(json.dumps({"code": code, "message": "refused", "requestId": "req"}).encode())
    return HTTPError("https://workers.example.com", status, "refused", headers, body)


def client(opener: FakeOpener, **options: Any) -> WorkerClient:
    return WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                        opener=opener, **options)  # type: ignore[arg-type]


class WorkerStorageDestinationTests(unittest.TestCase):
    def test_reads_the_organization_list_without_a_query_or_key(self) -> None:
        opener = FakeOpener([DESTINATIONS])
        listed = client(opener).storage_destinations()
        self.assertEqual(listed, DESTINATIONS)
        # The id is what update_snapshot_settings takes as storageDestinationId.
        self.assertEqual(listed["items"][0]["id"], "0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a")
        request = opener.requests[0]
        self.assertEqual((request.method, request.full_url), ("GET", "https://workers.example.com/api/v1/storage-destinations"))
        self.assertEqual(urlparse(request.full_url).query, "")
        self.assertEqual(request.get_header("Authorization"), "Bearer pgt_test-token")
        self.assertIsNone(request.get_header("Idempotency-key"))
        self.assertIsNone(request.data)

    def test_answers_an_empty_list(self) -> None:
        self.assertEqual(client(FakeOpener([{"items": []}])).storage_destinations(), {"items": []})

    def test_keeps_the_bounded_read_retry(self) -> None:
        opener = FakeOpener([refusal(503, "AUTH_UNAVAILABLE", "0"), DESTINATIONS])
        with patch("postgrip._internal.transport.time.sleep"):
            self.assertEqual(client(opener, enable_retries=True).storage_destinations(), DESTINATIONS)
        self.assertEqual(len(opener.requests), 2)

    def test_generated_client_reads_the_same_route(self) -> None:
        opener = FakeOpener([DESTINATIONS])
        self.assertEqual(client(opener).openapi.list_storage_destinations(), DESTINATIONS)
        self.assertEqual(urlparse(opener.requests[0].full_url).path, "/api/v1/storage-destinations")

    def test_async_client_shares_the_sync_route(self) -> None:
        async def run() -> None:
            opener = FakeOpener([DESTINATIONS])
            worker = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                                       opener=opener)  # type: ignore[arg-type]
            self.assertEqual(await worker.storage_destinations(), DESTINATIONS)
            self.assertEqual(urlparse(opener.requests[0].full_url).path, "/api/v1/storage-destinations")

        asyncio.run(run())

    def test_destination_type_declares_exactly_the_contract_fields(self) -> None:
        source = Path(worker_client.__file__).with_name("openapi.py").read_text(encoding="utf-8")
        classes = dict(re.findall(r"^class (_Schema\w+)\(.*?\):\n((?:    .*\n)+)", source, re.MULTILINE))
        fields = sorted(
            re.findall(r"^    (\w+):", classes["_SchemaStorageDestinationOptional"], re.MULTILINE)
            + re.findall(r"^    (\w+):", classes["_SchemaStorageDestination"], re.MULTILINE)
        )
        self.assertEqual(fields, sorted([
            "id", "name", "provider", "bucket", "region", "endpoint", "accountId", "prefix", "createdAt", "updatedAt",
        ]))


if __name__ == "__main__":
    unittest.main()
