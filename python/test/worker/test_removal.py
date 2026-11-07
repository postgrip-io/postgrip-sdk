from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import json
from typing import Any
import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse

from _http_fakes import FakeOpener
from postgrip.worker import AsyncWorkerClient, WorkerAPIError, WorkerClient
from postgrip.worker.openapi import OperationId

IMPACT = {
    "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11",
    "etag": '"worker-removal-5f2c"',
    "serviceCount": 2,
    "managedVolumeCount": 0,
    "unreachableVolumes": [],
    "projects": [
        {"id": "3c8e2a1f-5b7d-4e9c-a2f0-6d1b8e4c7a93", "name": "storefront", "exclusive": True, "usesAsDefault": False},
        {"id": "7a4d9e2c-1f3b-4c8a-b6e0-2d5f9a1c3e78", "name": "billing", "exclusive": False, "usesAsDefault": True},
    ],
}

REMOVED = {
    "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11",
    "shutdownRequested": True,
    "deletedServiceCount": 2,
    "deletedProjectCount": 1,
    "keptProjectCount": 1,
    "unassignedEnvironmentCount": 1,
    "clearedProjectDefaultCount": 1,
    "workerCleanup": {"attempted": 4, "failed": 0, "skipped": 0},
    "receipt": {"requestId": "req_01", "auditRecorded": True, "replayed": False},
}


def refusal(status: int, code: str) -> HTTPError:
    body = BytesIO(json.dumps({"code": code, "message": "refused", "requestId": "req"}).encode())
    return HTTPError("https://workers.example.com", status, "refused", Message(), body)


def client(opener: FakeOpener, **options: Any) -> WorkerClient:
    return WorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                        opener=opener, **options)  # type: ignore[arg-type]


class WorkerRemovalTests(unittest.TestCase):
    def test_removal_impact_reads_the_worker_impact_without_fences(self) -> None:
        opener = FakeOpener([IMPACT])
        self.assertEqual(client(opener).removal_impact("worker-1"), IMPACT)
        request = opener.requests[0]
        self.assertEqual((request.method, urlparse(request.full_url).path), ("GET", "/api/v1/workers/worker-1/removal-impact"))
        self.assertEqual(request.get_header("Authorization"), "Bearer pgt_test-token")
        self.assertIsNone(request.get_header("Idempotency-key"))
        self.assertIsNone(request.get_header("If-match"))
        self.assertIsNone(request.data)

    def test_remove_sends_both_fences_and_no_body(self) -> None:
        opener = FakeOpener([REMOVED])
        removed = client(opener).remove("worker-1", idempotency_key="remove-1", if_match=IMPACT["etag"])
        self.assertEqual(removed, REMOVED)
        request = opener.requests[0]
        self.assertEqual((request.method, urlparse(request.full_url).path), ("DELETE", "/api/v1/workers/worker-1"))
        self.assertEqual(request.get_header("Idempotency-key"), "remove-1")
        self.assertEqual(request.get_header("If-match"), '"worker-removal-5f2c"')
        self.assertIsNone(request.data)

    def test_remove_validates_its_fences_before_any_request(self) -> None:
        opener = FakeOpener([])
        worker = client(opener)
        for key, if_match in [("", '"impact"'), ("has space", '"impact"'), ("remove-1", ""),
                              ("remove-1", "  "), ("remove-1", '"impact"\r\nX-Injected: 1')]:
            with self.subTest(key=key, if_match=if_match), self.assertRaises(ValueError):
                worker.remove("worker-1", idempotency_key=key, if_match=if_match)
        self.assertEqual(opener.requests, [])

    def test_a_changed_impact_is_a_worker_api_error(self) -> None:
        opener = FakeOpener([refusal(412, "PRECONDITION_FAILED")])
        with self.assertRaises(WorkerAPIError) as raised:
            client(opener, enable_retries=True).remove("worker-1", idempotency_key="remove-1", if_match='"stale"')
        self.assertEqual((raised.exception.status, raised.exception.code), (412, "PRECONDITION_FAILED"))
        self.assertEqual(len(opener.requests), 1)

    def test_generated_client_forwards_if_match_only_where_declared(self) -> None:
        opener = FakeOpener([REMOVED, {}])
        worker = client(opener)
        worker.openapi.remove_worker("worker-1", idempotency_key="remove-1", if_match='"impact"')
        self.assertEqual(opener.requests[0].get_header("If-match"), '"impact"')
        worker._openapi_transport(  # noqa: SLF001
            OperationId.UPGRADE_WORKER,
            path_parameters={"workerId": "worker-1"},
            headers={"Idempotency-Key": "upgrade-1", "If-Match": '"impact"'},
        )
        self.assertIsNone(opener.requests[1].get_header("If-match"))

    def test_async_client_shares_the_sync_routes(self) -> None:
        async def run() -> None:
            opener = FakeOpener([IMPACT, REMOVED])
            worker = AsyncWorkerClient(base_url="https://workers.example.com", token="pgt_test-token",
                                       opener=opener)  # type: ignore[arg-type]
            impact = await worker.removal_impact("worker-1")
            self.assertEqual(
                await worker.remove("worker-1", idempotency_key="remove-1", if_match=impact["etag"]), REMOVED)
            self.assertEqual([request.method for request in opener.requests], ["GET", "DELETE"])
            self.assertEqual(opener.requests[1].get_header("If-match"), '"worker-removal-5f2c"')

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
