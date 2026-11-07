from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
import os
from threading import Event
import time
from typing import Any, Literal, cast
from urllib.request import OpenerDirector

from .._internal.config import validate_base_url, validate_idempotency_key, validate_management_token
from .._internal.http import REQUEST_CANCEL_EVENT, RequestCancelled, run_cancellable
from .._internal.pagination import iterate_pages, iterate_pages_async
from .._internal.transport import APIErrorFields, Executor, PostGripAPIError, RetryConfig, no_redirect_opener

from .openapi import (
    CheckWorkerResponseBody,
    CreateWorkerRequestBody,
    CreateWorkerResponseBody,
    CreateWorkerSnapshotResponseBody,
    GetWorkerJobResponseBody,
    GetWorkerResponseBody,
    GetWorkerSnapshotSettingsResponseBody,
    GetWorkerSnapshotStatusResponseBody,
    WorkerOrchestratorHealthResponseBody,
    ListWorkerAssignmentsResponseBody,
    ListWorkerJobsResponseBody,
    ListWorkerOperationalLogsResponseBody,
    ListWorkerSecurityLogsResponseBody,
    ListWorkerSnapshotsResponseBody,
    ListWorkersResponseBody,
    OpenAPIClient,
    OperationId,
    PlaceWorkerInMaintenanceResponseBody,
    ResumeWorkerFromMaintenanceResponseBody,
    UpdateWorkerSnapshotSettingsRequestBody,
    UpdateWorkerSnapshotSettingsResponseBody,
    UpgradeWorkerResponseBody,
    resolve_openapi_operation,
)

# createWorkerSnapshot waits up to 5 minutes on the server before it answers, so
# the call needs longer than the default 30-second timeout.
SNAPSHOT_RUN_TIMEOUT = 360.0


@dataclass(frozen=True)
class _CallPolicy:
    timeout: float
    no_retry_statuses: frozenset[int]


# createWorkerSnapshot's 502 and 504 answers are not kept against the
# Idempotency-Key, so an automatic resend, even with the same key, would take
# another snapshot; the caller reads the snapshot status first instead.
_OPERATION_CALL_POLICY: dict[OperationId, _CallPolicy] = {
    OperationId.CREATE_WORKER_SNAPSHOT: _CallPolicy(timeout=SNAPSHOT_RUN_TIMEOUT, no_retry_statuses=frozenset({502, 504})),
}

@dataclass(frozen=True)
class WorkerAPIError(PostGripAPIError):
    """A failed Worker request, with the same fields as before and the shared base."""

    @classmethod
    def _from_fields(cls, fields: APIErrorFields) -> WorkerAPIError:
        return cls(
            status=fields.status,
            code=fields.code,
            message=fields.message,
            request_id=fields.request_id,
            details=fields.details,
            retry_after=fields.retry_after,
        )

    def __str__(self) -> str:
        return f"postgrip-worker: {self.code} (HTTP {self.status}): {self.message}"


class WorkerClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        insecure_development: bool = False,
        enable_retries: bool = False,
        follow_interval: float = 2.0,
        timeout: float = 30.0,
        opener: OpenerDirector | None = None,
    ) -> None:
        base_url = validate_base_url("Worker", base_url, insecure_development=insecure_development)
        token = validate_management_token(token)
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token
        self._timeout = timeout
        self._follow_interval = max(follow_interval, 0.001)
        self._executor = Executor(
            plane="Worker",
            base_url=base_url,
            opener=no_redirect_opener(opener),
            management_token=token,
            retry=RetryConfig(enabled=enable_retries, max_attempts=3, max_delay=2.0, retry_after_max=30.0),
            timeout=timeout,
            create_error=WorkerAPIError._from_fields,
        )
        self.openapi = OpenAPIClient(self._openapi_transport)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> WorkerClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_WORKER_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    def health(self) -> WorkerOrchestratorHealthResponseBody:
        return cast(WorkerOrchestratorHealthResponseBody, self._request(OperationId.WORKER_ORCHESTRATOR_HEALTH))

    def _openapi_transport(
        self,
        operation_id: OperationId,
        body: Any = None,
        *,
        path_parameters: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = headers or {}
        idempotency_key = request_headers.get("Idempotency-Key")
        if idempotency_key is not None:
            validate_idempotency_key(idempotency_key)
        return self._request(
            operation_id,
            body=body,
            path=path_parameters,
            query=query,
            idempotency_key=idempotency_key,
        )

    def list(self, *, page_size: int | None = None, page_token: str | None = None,
             status: str | None = None, trust_state: str | None = None) -> ListWorkersResponseBody:
        return cast(ListWorkersResponseBody, self._request(OperationId.LIST_WORKERS, query={
            "pageSize": page_size, "pageToken": page_token, "status": status, "trustState": trust_state,
        }))

    def pages(self, **options: Any) -> Iterator[ListWorkersResponseBody]:
        page_token = options.pop("page_token", None)
        yield from iterate_pages(
            lambda next_token: self.list(page_token=next_token, **options), "nextPageToken", page_token,
        )

    def get(self, worker_id: str) -> GetWorkerResponseBody:
        return cast(GetWorkerResponseBody, self._request(OperationId.GET_WORKER, path={"workerId": worker_id}))

    def create(
        self,
        body: CreateWorkerRequestBody,
        *,
        idempotency_key: str,
    ) -> CreateWorkerResponseBody:
        """Create a pending Worker from durably persisted caller-owned values."""
        validate_idempotency_key(idempotency_key)
        return cast(CreateWorkerResponseBody, self._request(
            OperationId.CREATE_WORKER, body=body, idempotency_key=idempotency_key,
        ))

    def assignments(self, worker_id: str) -> ListWorkerAssignmentsResponseBody:
        return cast(ListWorkerAssignmentsResponseBody, self._request(OperationId.LIST_WORKER_ASSIGNMENTS, path={"workerId": worker_id}))

    def jobs(self, worker_id: str, *, page_size: int | None = None, page_token: str | None = None,
             state: str | None = None) -> ListWorkerJobsResponseBody:
        return cast(ListWorkerJobsResponseBody, self._request(OperationId.LIST_WORKER_JOBS,
            path={"workerId": worker_id}, query={"pageSize": page_size, "pageToken": page_token, "state": state}))

    def job_pages(self, worker_id: str, **options: Any) -> Iterator[ListWorkerJobsResponseBody]:
        page_token = options.pop("page_token", None)
        yield from iterate_pages(
            lambda next_token: self.jobs(worker_id, page_token=next_token, **options), "nextPageToken", page_token,
        )

    def job(self, worker_id: str, job_id: str) -> GetWorkerJobResponseBody:
        return cast(GetWorkerJobResponseBody, self._request(OperationId.GET_WORKER_JOB,
            path={"workerId": worker_id, "jobId": job_id}))

    def check(self, worker_id: str, *, idempotency_key: str) -> CheckWorkerResponseBody:
        return cast(CheckWorkerResponseBody, self._mutation(OperationId.CHECK_WORKER, worker_id, idempotency_key))

    def maintenance(self, worker_id: str, *, idempotency_key: str) -> PlaceWorkerInMaintenanceResponseBody:
        return cast(PlaceWorkerInMaintenanceResponseBody,
            self._mutation(OperationId.PLACE_WORKER_IN_MAINTENANCE, worker_id, idempotency_key))

    def resume(self, worker_id: str, *, idempotency_key: str) -> ResumeWorkerFromMaintenanceResponseBody:
        return cast(ResumeWorkerFromMaintenanceResponseBody,
            self._mutation(OperationId.RESUME_WORKER_FROM_MAINTENANCE, worker_id, idempotency_key))

    def upgrade(self, worker_id: str, *, idempotency_key: str) -> UpgradeWorkerResponseBody:
        return cast(UpgradeWorkerResponseBody, self._mutation(OperationId.UPGRADE_WORKER, worker_id, idempotency_key))

    def snapshot_status(self, worker_id: str) -> GetWorkerSnapshotStatusResponseBody:
        """Read the Worker's snapshot schedule and last run; ``enabled`` is false when snapshots are off."""
        return cast(GetWorkerSnapshotStatusResponseBody, self._request(
            OperationId.GET_WORKER_SNAPSHOT_STATUS, path={"workerId": worker_id}))

    def snapshots(self, worker_id: str) -> ListWorkerSnapshotsResponseBody:
        """List the Worker's archives in its storage destination, newest first. The list is not paged."""
        return cast(ListWorkerSnapshotsResponseBody, self._request(
            OperationId.LIST_WORKER_SNAPSHOTS, path={"workerId": worker_id}))

    def take_snapshot(self, worker_id: str, *, idempotency_key: str) -> CreateWorkerSnapshotResponseBody:
        """Run a snapshot on the Worker and wait for it.

        The server waits up to 5 minutes, so the call is allowed 6 minutes, and
        its 502 and 504 answers are never retried automatically: a ``504``
        ``SNAPSHOT_UNCONFIRMED`` run may still land, so read
        :meth:`snapshot_status` before resending with a new key.
        """
        return cast(CreateWorkerSnapshotResponseBody,
            self._mutation(OperationId.CREATE_WORKER_SNAPSHOT, worker_id, idempotency_key))

    def snapshot_settings(self, worker_id: str) -> GetWorkerSnapshotSettingsResponseBody:
        """Read the Worker's snapshot settings; the signing key is never answered, ``hasSigningKey`` reports one."""
        return cast(GetWorkerSnapshotSettingsResponseBody, self._request(
            OperationId.GET_WORKER_SNAPSHOT_SETTINGS, path={"workerId": worker_id}))

    def update_snapshot_settings(
        self,
        worker_id: str,
        body: UpdateWorkerSnapshotSettingsRequestBody,
        *,
        idempotency_key: str,
    ) -> UpdateWorkerSnapshotSettingsResponseBody:
        """Replace the Worker's whole snapshot settings record.

        Every field but ``enabled`` takes its zero value when omitted.
        ``signingKey`` is write-only: omit it to keep the stored key.
        """
        validate_idempotency_key(idempotency_key)
        return cast(UpdateWorkerSnapshotSettingsResponseBody, self._request(
            OperationId.UPDATE_WORKER_SNAPSHOT_SETTINGS, body=body, path={"workerId": worker_id},
            idempotency_key=idempotency_key,
        ))

    def operational_logs(
        self,
        worker_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        service: str | None = None,
        stream: Literal["stdout", "stderr"] | None = None,
    ) -> ListWorkerOperationalLogsResponseBody:
        return cast(ListWorkerOperationalLogsResponseBody, self._request(OperationId.LIST_WORKER_OPERATIONAL_LOGS,
            path={"workerId": worker_id}, query={
                "cursor": cursor, "limit": limit, "window": window, "since": since,
                "service": service, "stream": stream,
            }))

    def security_logs(
        self,
        worker_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        severity: Literal["debug", "info", "warn", "error"] | None = None,
        correlation_id: str | None = None,
        focus: str | None = None,
    ) -> ListWorkerSecurityLogsResponseBody:
        return cast(ListWorkerSecurityLogsResponseBody, self._request(OperationId.LIST_WORKER_SECURITY_LOGS,
            path={"workerId": worker_id}, query={
                "cursor": cursor, "limit": limit, "window": window, "since": since,
                "severity": severity, "correlationId": correlation_id, "focus": focus,
            }))

    def follow_operational_logs(
        self,
        worker_id: str,
        *,
        cancel: Event | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        service: str | None = None,
        stream: Literal["stdout", "stderr"] | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._follow(self.operational_logs, worker_id, cancel, {
            "cursor": cursor, "limit": limit, "window": window, "since": since,
            "service": service, "stream": stream,
        })

    def follow_security_logs(
        self,
        worker_id: str,
        *,
        cancel: Event | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        window: str | None = None,
        since: str | None = None,
        severity: Literal["debug", "info", "warn", "error"] | None = None,
        correlation_id: str | None = None,
        focus: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._follow(self.security_logs, worker_id, cancel, {
            "cursor": cursor, "limit": limit, "window": window, "since": since,
            "severity": severity, "correlation_id": correlation_id, "focus": focus,
        })

    def _follow(self, loader: Any, worker_id: str, cancel: Event | None, query: dict[str, Any]) -> Iterator[dict[str, Any]]:
        cursor = query.pop("cursor", None)
        last_id: int | None = None
        while cancel is None or not cancel.is_set():
            cancel_token = REQUEST_CANCEL_EVENT.set(cancel)
            try:
                page = loader(worker_id, cursor=cursor, **query)
            except RequestCancelled:
                return
            finally:
                REQUEST_CANCEL_EVENT.reset(cancel_token)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                if cancel is not None and cancel.is_set():
                    return
                entry_id = int(entry["id"])
                if last_id is None or entry_id > last_id:
                    last_id = entry_id
                    yield entry
            if not page["items"]:
                if cancel is not None:
                    if cancel.wait(self._follow_interval):
                        return
                else:
                    time.sleep(self._follow_interval)

    def _mutation(self, operation: OperationId, worker_id: str, idempotency_key: str) -> Any:
        validate_idempotency_key(idempotency_key)
        return self._request(operation, path={"workerId": worker_id}, idempotency_key=idempotency_key)

    @property
    def _opener(self) -> OpenerDirector:
        return self._executor.opener

    def _request(self, operation_id: OperationId, *, body: Any = None, path: Mapping[str, str] | None = None,
                 query: Mapping[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
        clean_query = {key: value for key, value in (query or {}).items() if value is not None}
        operation = resolve_openapi_operation(operation_id, path, clean_query)
        policy = _OPERATION_CALL_POLICY.get(operation_id)
        if policy is None:
            return self._executor.request(operation, body=body, idempotency_key=idempotency_key)
        # The policy raises the call's timeout; it never lowers a longer configured one.
        return self._executor.request(
            operation, body=body, idempotency_key=idempotency_key,
            timeout=max(self._timeout, policy.timeout), no_retry_statuses=policy.no_retry_statuses,
        )


class AsyncWorkerClient:
    def __init__(self, **options: Any) -> None:
        self._sync = WorkerClient(**options)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> AsyncWorkerClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_WORKER_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    async def _run(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        return await run_cancellable(callback, *args, **kwargs)

    async def list(self, **options: Any) -> ListWorkersResponseBody:
        return await self._run(self._sync.list, **options)

    async def health(self) -> WorkerOrchestratorHealthResponseBody:
        return await self._run(self._sync.health)

    async def pages(self, **options: Any) -> AsyncIterator[ListWorkersResponseBody]:
        page_token = options.pop("page_token", None)
        async for page in iterate_pages_async(
            lambda next_token: self.list(page_token=next_token, **options), "nextPageToken", page_token,
        ):
            yield page

    async def get(self, worker_id: str) -> GetWorkerResponseBody:
        return await self._run(self._sync.get, worker_id)

    async def create(
        self,
        body: CreateWorkerRequestBody,
        *,
        idempotency_key: str,
    ) -> CreateWorkerResponseBody:
        return await self._run(self._sync.create, body, idempotency_key=idempotency_key)

    async def assignments(self, worker_id: str) -> ListWorkerAssignmentsResponseBody:
        return await self._run(self._sync.assignments, worker_id)

    async def jobs(self, worker_id: str, **options: Any) -> ListWorkerJobsResponseBody:
        return await self._run(self._sync.jobs, worker_id, **options)

    async def job_pages(self, worker_id: str, **options: Any) -> AsyncIterator[ListWorkerJobsResponseBody]:
        page_token = options.pop("page_token", None)
        async for page in iterate_pages_async(
            lambda next_token: self.jobs(worker_id, page_token=next_token, **options), "nextPageToken", page_token,
        ):
            yield page

    async def job(self, worker_id: str, job_id: str) -> GetWorkerJobResponseBody:
        return await self._run(self._sync.job, worker_id, job_id)

    async def check(self, worker_id: str, *, idempotency_key: str) -> CheckWorkerResponseBody:
        return await self._run(self._sync.check, worker_id, idempotency_key=idempotency_key)

    async def maintenance(self, worker_id: str, *, idempotency_key: str) -> PlaceWorkerInMaintenanceResponseBody:
        return await self._run(self._sync.maintenance, worker_id, idempotency_key=idempotency_key)

    async def resume(self, worker_id: str, *, idempotency_key: str) -> ResumeWorkerFromMaintenanceResponseBody:
        return await self._run(self._sync.resume, worker_id, idempotency_key=idempotency_key)

    async def upgrade(self, worker_id: str, *, idempotency_key: str) -> UpgradeWorkerResponseBody:
        return await self._run(self._sync.upgrade, worker_id, idempotency_key=idempotency_key)

    async def snapshot_status(self, worker_id: str) -> GetWorkerSnapshotStatusResponseBody:
        return await self._run(self._sync.snapshot_status, worker_id)

    async def snapshots(self, worker_id: str) -> ListWorkerSnapshotsResponseBody:
        return await self._run(self._sync.snapshots, worker_id)

    async def take_snapshot(self, worker_id: str, *, idempotency_key: str) -> CreateWorkerSnapshotResponseBody:
        return await self._run(self._sync.take_snapshot, worker_id, idempotency_key=idempotency_key)

    async def snapshot_settings(self, worker_id: str) -> GetWorkerSnapshotSettingsResponseBody:
        return await self._run(self._sync.snapshot_settings, worker_id)

    async def update_snapshot_settings(
        self,
        worker_id: str,
        body: UpdateWorkerSnapshotSettingsRequestBody,
        *,
        idempotency_key: str,
    ) -> UpdateWorkerSnapshotSettingsResponseBody:
        return await self._run(self._sync.update_snapshot_settings, worker_id, body, idempotency_key=idempotency_key)

    async def operational_logs(self, worker_id: str, **query: Any) -> ListWorkerOperationalLogsResponseBody:
        return await self._run(self._sync.operational_logs, worker_id, **query)

    async def security_logs(self, worker_id: str, **query: Any) -> ListWorkerSecurityLogsResponseBody:
        return await self._run(self._sync.security_logs, worker_id, **query)

    async def follow_operational_logs(self, worker_id: str, **query: Any) -> AsyncIterator[dict[str, Any]]:
        async for entry in self._follow(self._sync.operational_logs, worker_id, query):
            yield entry

    async def follow_security_logs(self, worker_id: str, **query: Any) -> AsyncIterator[dict[str, Any]]:
        async for entry in self._follow(self._sync.security_logs, worker_id, query):
            yield entry

    async def _follow(self, loader: Any, worker_id: str, query: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        cursor = query.pop("cursor", None)
        last_id: int | None = None
        while True:
            page = await self._run(loader, worker_id, cursor=cursor, **query)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                await asyncio.sleep(0)
                entry_id = int(entry["id"])
                if last_id is None or entry_id > last_id:
                    last_id = entry_id
                    yield entry
            if not page["items"]:
                await asyncio.sleep(self._sync._follow_interval)
