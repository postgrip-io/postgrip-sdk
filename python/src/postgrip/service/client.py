from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPConnection, HTTPSConnection
import json
import math
import os
import random
import socket
from threading import Event, Thread
import time
from typing import Any, Callable, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, OpenerDirector, Request, build_opener

from .._internal.config import validate_base_url, validate_idempotency_key, validate_management_token
from .._internal.pagination import iterate_pages, iterate_pages_async

from .administration_types import (
    AsyncDeclarativeConfigurationAdministration,
    AsyncConfigurationOperationsAdministration,
    AsyncDomainsAdministration,
    AsyncDNSAdministration,
    AsyncEnvironmentsAdministration,
    AsyncManagedVolumesAdministration,
    AsyncProjectsAdministration,
    AsyncPromotionsAdministration,
    AsyncRepositoriesAdministration,
    AsyncReleaseGroupsAdministration,
    AsyncRetentionAdministration,
    AsyncTargetServicesAdministration,
    AsyncVariablesAdministration,
    ConfigurationOperationsAdministration,
    DeclarativeConfigurationAdministration,
    DomainsAdministration,
    DNSAdministration,
    EnvironmentsAdministration,
    ManagedVolumesAdministration,
    ProjectsAdministration,
    PromotionsAdministration,
    RepositoriesAdministration,
    ReleaseGroupsAdministration,
    RetentionAdministration,
    TargetServicesAdministration,
    VariablesAdministration,
)
from .openapi import (
    CancelServiceDeploymentResponseBody,
    CheckServiceResponseBody,
    DeployServiceResponseBody,
    GetServiceDeploymentResponseBody,
    GetServiceResponseBody,
    GetServiceStatusResponseBody,
    ListServiceDeploymentsResponseBody,
    ListServiceEnvironmentsResponseBody,
    ListServiceLogsResponseBody,
    ListServicesResponseBody,
    OpenAPIClient,
    OperationId,
    PreviewServiceDeployResponseBody,
    RedeployServiceResponseBody,
    ResolveServiceEnvironmentResponseBody,
    ResolveServiceResponseBody,
    RestartServiceRuntimeResponseBody,
    RollbackServiceDeploymentResponseBody,
    StartServiceRuntimeResponseBody,
    StopServiceRuntimeResponseBody,
    resolve_openapi_operation,
)

_RETRYABLE_STATUS = {408, 429, 502, 503, 504}
_MAX_RESPONSE_BYTES = 4 << 20
_MAXIMUM_RETRY_ATTEMPTS = 3
_MAXIMUM_RETRY_DELAY = 2.0
_MAXIMUM_RETRY_AFTER_DELAY = 30.0
_REQUEST_CANCEL_EVENT: ContextVar[Event | None] = ContextVar("postgrip_service_request_cancel", default=None)

_ADMINISTRATION_OPERATION_GROUPS: dict[str, tuple[str, ...]] = {
    "target_services": (
        "attach_target_service", "update_target_service", "get_target_service_removal_impact",
        "detach_target_service", "put_target_service_connection", "clear_target_service_connection",
    ),
    "projects": (
        "create_service_project", "update_service_project", "get_service_project_removal_impact",
        "delete_service_project",
    ),
    "environments": (
        "get_service_environment", "create_service_environment", "update_service_environment",
        "preview_service_environment_reassignment", "reassign_service_environment",
        "get_service_environment_removal_impact", "delete_service_environment",
    ),
    "managed_volumes": (
        "list_service_volumes", "create_service_volume", "get_service_volume",
        "get_service_volume_removal_impact", "delete_service_volume", "bind_service_volume",
        "update_service_volume_binding", "unbind_service_volume",
    ),
    "domains": (
        "list_service_domains", "create_service_domain", "update_service_domain", "delete_service_domain",
        "get_service_domain_verification", "verify_service_domain",
    ),
    "dns": (
        "get_service_dns_canonical_state", "list_service_dns_plans",
        "create_service_dns_plan", "get_service_dns_plan", "apply_service_dns_plan",
        "report_service_dns_provider_result", "rollback_service_dns_plan",
        "get_service_dns_failover_policy", "update_service_dns_failover_policy",
        "request_service_dns_failover",
    ),
    "variables": (
        "list_service_variables", "create_service_variable", "update_service_variable",
        "delete_service_variable", "put_service_variable_value", "clear_service_variable_value",
        "apply_service_variables",
    ),
    "repositories": (
        "get_service_repository", "update_service_repository", "put_service_repository_credential",
        "clear_service_repository_credential", "refresh_service_repository_credential",
        "list_git_hub_app_repositories", "preview_git_hub_repository_adoption",
        "adopt_git_hub_repository",
    ),
    "promotions": (
        "list_service_promotions", "preview_service_promotion", "promote_service_deployment",
    ),
    "release_groups": (
        "list_service_release_groups", "preview_service_release_group", "create_service_release_group",
        "get_service_release_group", "list_service_release_group_events", "cancel_service_release_group",
        "retry_service_release_group",
    ),
    "retention": (
        "get_service_build_log_settings", "update_service_build_log_settings", "trim_service_build_logs",
        "flush_service_build_logs", "get_service_runtime_log_settings",
        "update_service_runtime_log_settings", "trim_service_runtime_logs", "flush_service_runtime_logs",
    ),
    "configuration_operations": (
        "list_service_configuration_operations", "get_service_configuration_operation",
        "retry_service_configuration_operation",
    ),
    "declarative_configuration": (
        "validate_post_grip_configuration", "get_post_grip_configuration_stack",
        "create_post_grip_configuration_plan", "get_post_grip_configuration_plan",
        "list_post_grip_configuration_plan_actions", "apply_post_grip_configuration_plan",
        "get_post_grip_configuration_stack_operation",
        "list_post_grip_configuration_stack_operation_actions",
        "retry_post_grip_configuration_stack_operation",
        "resubmit_post_grip_configuration_secret_inputs",
    ),
}


class _RequestCancelled(Exception):
    pass


class _CancellationAwareConnection:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cancel_event = _REQUEST_CANCEL_EVENT.get()
        self._request_done = Event()
        self._receiving_response = False
        self._response_open = False
        self._active_socket: socket.socket | None = None
        if self._cancel_event is not None:
            Thread(target=self._watch_for_cancellation, daemon=True).start()

    def _watch_for_cancellation(self) -> None:
        assert self._cancel_event is not None
        while not self._request_done.wait(0.01):
            if self._cancel_event.is_set():
                active_socket = self._active_socket
                if active_socket is not None:
                    try:
                        active_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                super().close()
                return

    def connect(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise OSError("request cancelled")
        super().connect()
        self._active_socket = self.sock
        if self._cancel_event is not None and self._cancel_event.is_set():
            try:
                if self._active_socket is not None:
                    self._active_socket.shutdown(socket.SHUT_RDWR)
            finally:
                super().close()
            raise OSError("request cancelled")

    def getresponse(self) -> Any:
        self._receiving_response = True
        try:
            response = super().getresponse()
        except BaseException:
            self._request_done.set()
            raise
        finally:
            self._receiving_response = False
        self._response_open = True
        close_response = response.close

        def close() -> None:
            try:
                close_response()
            finally:
                self._response_open = False
                self._request_done.set()

        response.close = close
        return response

    def close(self) -> None:
        super().close()
        if not self._receiving_response and not self._response_open:
            self._request_done.set()


class _CancellationAwareHTTPConnection(_CancellationAwareConnection, HTTPConnection):
    pass


class _CancellationAwareHTTPSConnection(_CancellationAwareConnection, HTTPSConnection):
    pass


class _CancellationAwareHTTPHandler(HTTPHandler):
    handler_order = 400

    def http_open(self, request: Request) -> Any:
        return self.do_open(_CancellationAwareHTTPConnection, request)


class _CancellationAwareHTTPSHandler(HTTPSHandler):
    handler_order = 400

    def https_open(self, request: Request) -> Any:
        return self.do_open(
            _CancellationAwareHTTPSConnection,
            request,
            context=getattr(self, "_context", None),
            check_hostname=getattr(self, "_check_hostname", None),
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _redirect_safe_opener(opener: OpenerDirector | None) -> OpenerDirector:
    https_context = None
    https_check_hostname = None
    if opener is not None:
        for handler in opener.handlers:
            if isinstance(handler, HTTPSHandler):
                https_context = getattr(handler, "_context", None)
                https_check_hostname = getattr(handler, "_check_hostname", None)
                break
    cancellation_handlers = (
        _CancellationAwareHTTPHandler(),
        _CancellationAwareHTTPSHandler(context=https_context, check_hostname=https_check_hostname),
    )
    if opener is None:
        return build_opener(_NoRedirect(), *cancellation_handlers)
    redirect_methods = ("http_error_301", "http_error_302", "http_error_303", "http_error_307", "http_error_308")
    handlers = [handler for handler in opener.handlers if not any(hasattr(handler, name) for name in redirect_methods)]
    if len(handlers) == len(opener.handlers):
        opener.add_handler(_NoRedirect())
        for handler in cancellation_handlers:
            opener.add_handler(handler)
        return opener
    return build_opener(*handlers, _NoRedirect(), *cancellation_handlers)


@dataclass(frozen=True)
class ServiceAPIError(Exception):
    status: int
    code: str
    message: str
    request_id: str = ""
    details: Mapping[str, Any] | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        return f"postgrip-service: {self.code} (HTTP {self.status}): {self.message}"


@dataclass(frozen=True)
class ServiceReference:
    source: Literal["target", "project"]
    id: str

    @classmethod
    def from_service(cls, service: Mapping[str, Any]) -> ServiceReference:
        source = service.get("source")
        identifier = service.get("id")
        if source not in {"target", "project"} or not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("service must contain a target or project source and non-empty id")
        return cls(cast(Literal["target", "project"], source), identifier)

    def path(self) -> dict[str, str]:
        if self.source not in {"target", "project"} or not self.id.strip():
            raise ValueError("service reference must contain a target or project source and non-empty id")
        return {"source": self.source, "serviceId": self.id}


class _AdministrationGroup:
    """A bounded view over generated, fully annotated administration methods."""

    def __init__(self, generated: OpenAPIClient, operations: tuple[str, ...]) -> None:
        self._generated = generated
        self._operations = frozenset(operations)

    def __dir__(self) -> list[str]:
        return sorted(self._operations)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name not in self._operations:
            raise AttributeError(name)
        return cast(Callable[..., Any], getattr(self._generated, name))


class ServiceAdministration:
    """Grouped access to all 87 generated Service-administration operations."""

    target_services: TargetServicesAdministration
    projects: ProjectsAdministration
    environments: EnvironmentsAdministration
    managed_volumes: ManagedVolumesAdministration
    domains: DomainsAdministration
    dns: DNSAdministration
    variables: VariablesAdministration
    repositories: RepositoriesAdministration
    promotions: PromotionsAdministration
    release_groups: ReleaseGroupsAdministration
    retention: RetentionAdministration
    configuration_operations: ConfigurationOperationsAdministration
    declarative_configuration: DeclarativeConfigurationAdministration

    def __init__(self, transport: Callable[..., Any]) -> None:
        generated = OpenAPIClient(transport)
        self.target_services = cast(TargetServicesAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["target_services"]))
        self.projects = cast(ProjectsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["projects"]))
        self.environments = cast(EnvironmentsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["environments"]))
        self.managed_volumes = cast(ManagedVolumesAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["managed_volumes"]))
        self.domains = cast(DomainsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["domains"]))
        self.dns = cast(DNSAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["dns"]))
        self.variables = cast(VariablesAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["variables"]))
        self.repositories = cast(RepositoriesAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["repositories"]))
        self.promotions = cast(PromotionsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["promotions"]))
        self.release_groups = cast(ReleaseGroupsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["release_groups"]))
        self.retention = cast(RetentionAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["retention"]))
        self.configuration_operations = cast(ConfigurationOperationsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["configuration_operations"]))
        self.declarative_configuration = cast(DeclarativeConfigurationAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["declarative_configuration"]))


class AsyncServiceAdministration:
    """Async grouped administration facade backed by the synchronous transport."""

    target_services: AsyncTargetServicesAdministration
    projects: AsyncProjectsAdministration
    environments: AsyncEnvironmentsAdministration
    managed_volumes: AsyncManagedVolumesAdministration
    domains: AsyncDomainsAdministration
    dns: AsyncDNSAdministration
    variables: AsyncVariablesAdministration
    repositories: AsyncRepositoriesAdministration
    promotions: AsyncPromotionsAdministration
    release_groups: AsyncReleaseGroupsAdministration
    retention: AsyncRetentionAdministration
    configuration_operations: AsyncConfigurationOperationsAdministration
    declarative_configuration: AsyncDeclarativeConfigurationAdministration

    def __init__(self, client: AsyncServiceClient, sync: ServiceAdministration) -> None:
        self.target_services = cast(AsyncTargetServicesAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.target_services)))
        self.projects = cast(AsyncProjectsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.projects)))
        self.environments = cast(AsyncEnvironmentsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.environments)))
        self.managed_volumes = cast(AsyncManagedVolumesAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.managed_volumes)))
        self.domains = cast(AsyncDomainsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.domains)))
        self.dns = cast(AsyncDNSAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.dns)))
        self.variables = cast(AsyncVariablesAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.variables)))
        self.repositories = cast(AsyncRepositoriesAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.repositories)))
        self.promotions = cast(AsyncPromotionsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.promotions)))
        self.release_groups = cast(AsyncReleaseGroupsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.release_groups)))
        self.retention = cast(AsyncRetentionAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.retention)))
        self.configuration_operations = cast(AsyncConfigurationOperationsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.configuration_operations)))
        self.declarative_configuration = cast(AsyncDeclarativeConfigurationAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.declarative_configuration)))


class _AsyncAdministrationGroup:
    def __init__(self, client: AsyncServiceClient, sync: _AdministrationGroup) -> None:
        self._client = client
        self._sync = sync

    def __dir__(self) -> list[str]:
        return dir(self._sync)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        sync_method = getattr(self._sync, name)

        async def invoke(*args: Any, **kwargs: Any) -> Any:
            return await self._client._run(sync_method, *args, **kwargs)

        return invoke


class ServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        insecure_development: bool = False,
        enable_retries: bool = False,
        retry_max_attempts: int = 3,
        retry_max_delay: float = 2.0,
        retry_after_max_delay: float = 30.0,
        follow_interval: float = 2.0,
        timeout: float = 30.0,
        opener: OpenerDirector | None = None,
    ) -> None:
        base_url = validate_base_url("Service", base_url, insecure_development=insecure_development)
        token = validate_management_token(token)
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token
        self._enable_retries = enable_retries
        self._retry_max_attempts, self._retry_max_delay, self._retry_after_max_delay = _configured_retry_limits(
            retry_max_attempts, retry_max_delay, retry_after_max_delay,
        )
        self._follow_interval = max(follow_interval, 0.001)
        self._timeout = timeout
        self._opener = _redirect_safe_opener(opener)
        self.openapi = OpenAPIClient(self._openapi_transport)
        self.administration = ServiceAdministration(self._openapi_transport)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> ServiceClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_SERVICE_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    def list(
        self,
        *,
        kind: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        worker_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ListServicesResponseBody:
        return cast(ListServicesResponseBody, self._request(OperationId.LIST_SERVICES, query={
            "kind": kind, "mode": mode, "status": status, "worker": worker_id, "limit": limit, "cursor": cursor,
        }))

    def pages(self, **options: Any) -> Iterator[ListServicesResponseBody]:
        cursor = options.pop("cursor", None)
        yield from iterate_pages(
            lambda next_cursor: self.list(cursor=next_cursor, **options), "nextCursor", cursor,
        )

    def resolve(self, value: str) -> ResolveServiceResponseBody:
        return cast(ResolveServiceResponseBody, self._request(OperationId.RESOLVE_SERVICE, query={"value": value}))

    def for_service(self, service: ServiceReference | Mapping[str, Any]) -> ScopedServiceClient:
        reference = service if isinstance(service, ServiceReference) else ServiceReference.from_service(service)
        reference.path()
        return ScopedServiceClient(self, reference)

    def get(self, service: ServiceReference) -> GetServiceResponseBody:
        return cast(GetServiceResponseBody, self._request(OperationId.GET_SERVICE, path=service.path()))

    def status(self, service: ServiceReference, *, environment: str | None = None) -> GetServiceStatusResponseBody:
        return cast(GetServiceStatusResponseBody, self._request(
            OperationId.GET_SERVICE_STATUS, path=service.path(), query={"environment": environment},
        ))

    def environments(
        self, service: ServiceReference, *, limit: int | None = None, cursor: str | None = None,
    ) -> ListServiceEnvironmentsResponseBody:
        return cast(ListServiceEnvironmentsResponseBody, self._request(
            OperationId.LIST_SERVICE_ENVIRONMENTS, path=service.path(), query={"limit": limit, "cursor": cursor},
        ))

    def environment_pages(self, service: ServiceReference, **options: Any) -> Iterator[ListServiceEnvironmentsResponseBody]:
        cursor = options.pop("cursor", None)
        yield from iterate_pages(
            lambda next_cursor: self.environments(service, cursor=next_cursor, **options), "nextCursor", cursor,
        )

    def environment(self, project_id: str, value: str) -> ResolveServiceEnvironmentResponseBody:
        return cast(ResolveServiceEnvironmentResponseBody, self._request(
            OperationId.RESOLVE_SERVICE_ENVIRONMENT, path={"serviceId": project_id}, query={"value": value},
        ))

    def deployments(
        self,
        service: ServiceReference,
        *,
        environment: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ListServiceDeploymentsResponseBody:
        return cast(ListServiceDeploymentsResponseBody, self._request(
            OperationId.LIST_SERVICE_DEPLOYMENTS, path=service.path(),
            query={"environment": environment, "status": status, "limit": limit, "cursor": cursor},
        ))

    def deployment_pages(self, service: ServiceReference, **options: Any) -> Iterator[ListServiceDeploymentsResponseBody]:
        cursor = options.pop("cursor", None)
        yield from iterate_pages(
            lambda next_cursor: self.deployments(service, cursor=next_cursor, **options), "nextCursor", cursor,
        )

    def deployment(self, project_id: str, deployment_id: str) -> GetServiceDeploymentResponseBody:
        return cast(GetServiceDeploymentResponseBody, self._request(
            OperationId.GET_SERVICE_DEPLOYMENT,
            path={"serviceId": project_id, "deploymentId": deployment_id},
        ))

    def logs(
        self,
        service: ServiceReference,
        *,
        kind: Literal["build", "runtime"] | None = None,
        environment_id: str | None = None,
        deployment_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        follow: bool | None = None,
    ) -> ListServiceLogsResponseBody:
        return cast(ListServiceLogsResponseBody, self._request(
            OperationId.LIST_SERVICE_LOGS, path=service.path(), query={
                "kind": kind, "environment": environment_id, "deployment": deployment_id,
                "limit": limit, "cursor": cursor, "follow": follow,
            },
        ))

    def follow_logs(
        self,
        service: ServiceReference,
        *,
        cancel: Event | None = None,
        kind: Literal["build", "runtime"] | None = None,
        environment_id: str | None = None,
        deployment_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        while cancel is None or not cancel.is_set():
            cancel_token = _REQUEST_CANCEL_EVENT.set(cancel)
            try:
                page = self.logs(
                    service, kind=kind, environment_id=environment_id, deployment_id=deployment_id,
                    limit=limit, cursor=cursor, follow=True,
                )
            except _RequestCancelled:
                return
            finally:
                _REQUEST_CANCEL_EVENT.reset(cancel_token)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                if cancel is not None and cancel.is_set():
                    return
                yield entry
            if not page["items"]:
                delay = float(page.get("pollAfterMs", 0)) / 1000.0
                if delay <= 0:
                    delay = self._follow_interval
                if cancel is not None:
                    if cancel.wait(delay):
                        return
                else:
                    time.sleep(delay)

    def check(
        self, service: ServiceReference, *, environment_id: str | None = None, idempotency_key: str,
    ) -> CheckServiceResponseBody:
        return cast(CheckServiceResponseBody, self._mutation(
            OperationId.CHECK_SERVICE, path=service.path(), body={"environmentId": environment_id},
            idempotency_key=idempotency_key,
        ))

    def preview_deploy(
        self, project_id: str, *, environment: str | None = None, branch: str | None = None,
    ) -> PreviewServiceDeployResponseBody:
        return cast(PreviewServiceDeployResponseBody, self._request(
            OperationId.PREVIEW_SERVICE_DEPLOY, path={"serviceId": project_id},
            query={"environment": environment, "branch": branch},
        ))

    def deploy(
        self,
        project_id: str,
        *,
        expected_commit_sha: str,
        idempotency_key: str,
        environment_id: str | None = None,
        branch: str | None = None,
    ) -> DeployServiceResponseBody:
        return cast(DeployServiceResponseBody, self._mutation(
            OperationId.DEPLOY_SERVICE, path={"serviceId": project_id}, body={
                "environmentId": environment_id, "branch": branch, "expectedCommitSha": expected_commit_sha,
            }, idempotency_key=idempotency_key,
        ))

    def redeploy(
        self,
        project_id: str,
        *,
        idempotency_key: str,
        environment_id: str | None = None,
        deployment_id: str | None = None,
    ) -> RedeployServiceResponseBody:
        return cast(RedeployServiceResponseBody, self._mutation(
            OperationId.REDEPLOY_SERVICE, path={"serviceId": project_id},
            body={"environmentId": environment_id, "deploymentId": deployment_id},
            idempotency_key=idempotency_key,
        ))

    def cancel(self, project_id: str, deployment_id: str, *, idempotency_key: str) -> CancelServiceDeploymentResponseBody:
        return cast(CancelServiceDeploymentResponseBody, self._mutation(
            OperationId.CANCEL_SERVICE_DEPLOYMENT,
            path={"serviceId": project_id, "deploymentId": deployment_id}, idempotency_key=idempotency_key,
        ))

    def rollback(self, project_id: str, deployment_id: str, *, idempotency_key: str) -> RollbackServiceDeploymentResponseBody:
        return cast(RollbackServiceDeploymentResponseBody, self._mutation(
            OperationId.ROLLBACK_SERVICE_DEPLOYMENT,
            path={"serviceId": project_id, "deploymentId": deployment_id}, idempotency_key=idempotency_key,
        ))

    def start(
        self, project_id: str, environment_id: str, *, expected_deployment_id: str, idempotency_key: str,
    ) -> StartServiceRuntimeResponseBody:
        return cast(StartServiceRuntimeResponseBody, self._runtime_mutation(
            OperationId.START_SERVICE_RUNTIME, project_id, environment_id, expected_deployment_id, idempotency_key,
        ))

    def stop(
        self, project_id: str, environment_id: str, *, expected_deployment_id: str, idempotency_key: str,
    ) -> StopServiceRuntimeResponseBody:
        return cast(StopServiceRuntimeResponseBody, self._runtime_mutation(
            OperationId.STOP_SERVICE_RUNTIME, project_id, environment_id, expected_deployment_id, idempotency_key,
        ))

    def restart(
        self, project_id: str, environment_id: str, *, expected_deployment_id: str, idempotency_key: str,
    ) -> RestartServiceRuntimeResponseBody:
        return cast(RestartServiceRuntimeResponseBody, self._runtime_mutation(
            OperationId.RESTART_SERVICE_RUNTIME, project_id, environment_id, expected_deployment_id, idempotency_key,
        ))

    def _runtime_mutation(
        self, operation: OperationId, project_id: str, environment_id: str,
        expected_deployment_id: str, idempotency_key: str,
    ) -> Any:
        return self._mutation(
            operation, path={"serviceId": project_id, "environmentId": environment_id},
            body={"expectedDeploymentId": expected_deployment_id}, idempotency_key=idempotency_key,
        )

    def _mutation(
        self,
        operation: OperationId,
        *,
        path: Mapping[str, str],
        idempotency_key: str,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        validate_idempotency_key(idempotency_key)
        return self._request(operation, path=path, body=body, idempotency_key=idempotency_key)

    def _request(
        self,
        operation_id: OperationId,
        *,
        path: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        if_match: str | None = None,
    ) -> Any:
        clean_query = {key: value for key, value in (query or {}).items() if value is not None}
        clean_body = {key: value for key, value in (body or {}).items() if value is not None} if body is not None else None
        operation = resolve_openapi_operation(operation_id, path, clean_query)
        attempts = self._retry_max_attempts if self._enable_retries and (operation.method == "GET" or idempotency_key) else 1
        endpoint = urljoin(self._base_url, operation.path.lstrip("/"))
        encoded_body = json.dumps(clean_body).encode() if clean_body is not None else None
        cancel_event = _REQUEST_CANCEL_EVENT.get()
        for attempt in range(1, attempts + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise _RequestCancelled
            request = Request(endpoint, data=encoded_body, method=operation.method, headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                **({"Content-Type": "application/json"} if encoded_body is not None else {}),
                **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
                **({"If-Match": if_match} if if_match else {}),
            })
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    return _decode_success(response)
            except HTTPError as error:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                api_error = _decode_http_error(error, self._retry_after_max_delay)
                if attempt < attempts and error.code in _RETRYABLE_STATUS:
                    retry_after = api_error.retry_after if error.code in {429, 503} else None
                    delay = retry_after if retry_after is not None else _jitter(attempt, self._retry_max_delay)
                    if cancel_event is not None:
                        if cancel_event.wait(delay):
                            raise _RequestCancelled
                    else:
                        time.sleep(delay)
                    continue
                raise api_error from None
            except URLError:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                if attempt < attempts:
                    delay = _jitter(attempt, self._retry_max_delay)
                    if cancel_event is not None:
                        if cancel_event.wait(delay):
                            raise _RequestCancelled
                    else:
                        time.sleep(delay)
                    continue
                raise
            except Exception:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RequestCancelled from None
                raise
        raise RuntimeError("PostGrip Service request attempts exhausted")

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
        if_match = request_headers.get("If-Match")
        if if_match is not None and (not if_match.strip() or "\r" in if_match or "\n" in if_match):
            raise ValueError("if_match must be a non-empty HTTP ETag without line breaks")
        return self._request(
            operation_id,
            path=path_parameters,
            query=query,
            body=cast(Mapping[str, Any] | None, body),
            idempotency_key=idempotency_key,
            if_match=if_match,
        )


class ScopedServiceClient:
    def __init__(self, client: ServiceClient, reference: ServiceReference) -> None:
        self._client = client
        self.reference = reference

    def get(self) -> GetServiceResponseBody:
        return self._client.get(self.reference)

    def status(self, *, environment: str | None = None) -> GetServiceStatusResponseBody:
        return self._client.status(self.reference, environment=environment)

    def environments(self, **options: Any) -> ListServiceEnvironmentsResponseBody:
        return self._client.environments(self.reference, **options)

    def deployments(self, **options: Any) -> ListServiceDeploymentsResponseBody:
        return self._client.deployments(self.reference, **options)

    def logs(self, **options: Any) -> ListServiceLogsResponseBody:
        return self._client.logs(self.reference, **options)

    def follow_logs(self, **options: Any) -> Iterator[dict[str, Any]]:
        yield from self._client.follow_logs(self.reference, **options)

    def check(self, **options: Any) -> CheckServiceResponseBody:
        return self._client.check(self.reference, **options)


class AsyncServiceClient:
    def __init__(self, **options: Any) -> None:
        self._sync = ServiceClient(**options)
        self.administration = AsyncServiceAdministration(self, self._sync.administration)

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **options: Any,
    ) -> AsyncServiceClient:
        values = os.environ if environ is None else environ
        options.setdefault("base_url", values.get("POSTGRIP_SERVICE_URL") or values.get("POSTGRIP_URL", ""))
        options.setdefault("token", values.get("POSTGRIP_TOKEN", ""))
        return cls(**options)

    async def _run(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        cancel_event = Event()
        token = _REQUEST_CANCEL_EVENT.set(cancel_event)
        try:
            return await asyncio.to_thread(callback, *args, **kwargs)
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        finally:
            _REQUEST_CANCEL_EVENT.reset(token)

    async def list(self, **options: Any) -> ListServicesResponseBody:
        return await self._run(self._sync.list, **options)

    async def pages(self, **options: Any) -> AsyncIterator[ListServicesResponseBody]:
        cursor = options.pop("cursor", None)
        async for page in iterate_pages_async(
            lambda next_cursor: self.list(cursor=next_cursor, **options), "nextCursor", cursor,
        ):
            yield page

    async def resolve(self, value: str) -> ResolveServiceResponseBody:
        return await self._run(self._sync.resolve, value)

    async def get(self, service: ServiceReference) -> GetServiceResponseBody:
        return await self._run(self._sync.get, service)

    async def status(self, service: ServiceReference, **options: Any) -> GetServiceStatusResponseBody:
        return await self._run(self._sync.status, service, **options)

    async def environments(self, service: ServiceReference, **options: Any) -> ListServiceEnvironmentsResponseBody:
        return await self._run(self._sync.environments, service, **options)

    async def environment(self, project_id: str, value: str) -> ResolveServiceEnvironmentResponseBody:
        return await self._run(self._sync.environment, project_id, value)

    async def deployments(self, service: ServiceReference, **options: Any) -> ListServiceDeploymentsResponseBody:
        return await self._run(self._sync.deployments, service, **options)

    async def deployment(self, project_id: str, deployment_id: str) -> GetServiceDeploymentResponseBody:
        return await self._run(self._sync.deployment, project_id, deployment_id)

    async def logs(self, service: ServiceReference, **options: Any) -> ListServiceLogsResponseBody:
        return await self._run(self._sync.logs, service, **options)

    async def follow_logs(self, service: ServiceReference, **query: Any) -> AsyncIterator[dict[str, Any]]:
        cursor = query.pop("cursor", None)
        while True:
            page = await self.logs(service, cursor=cursor, follow=True, **query)
            cursor = page["nextCursor"]
            for entry in page["items"]:
                await asyncio.sleep(0)
                yield entry
            if not page["items"]:
                delay = float(page.get("pollAfterMs", 0)) / 1000.0
                if delay <= 0:
                    delay = self._sync._follow_interval
                await asyncio.sleep(delay)

    async def check(self, service: ServiceReference, **options: Any) -> CheckServiceResponseBody:
        return await self._run(self._sync.check, service, **options)

    async def preview_deploy(self, project_id: str, **options: Any) -> PreviewServiceDeployResponseBody:
        return await self._run(self._sync.preview_deploy, project_id, **options)

    async def deploy(self, project_id: str, **options: Any) -> DeployServiceResponseBody:
        return await self._run(self._sync.deploy, project_id, **options)

    async def redeploy(self, project_id: str, **options: Any) -> RedeployServiceResponseBody:
        return await self._run(self._sync.redeploy, project_id, **options)

    async def cancel(self, project_id: str, deployment_id: str, **options: Any) -> CancelServiceDeploymentResponseBody:
        return await self._run(self._sync.cancel, project_id, deployment_id, **options)

    async def rollback(self, project_id: str, deployment_id: str, **options: Any) -> RollbackServiceDeploymentResponseBody:
        return await self._run(self._sync.rollback, project_id, deployment_id, **options)

    async def start(self, project_id: str, environment_id: str, **options: Any) -> StartServiceRuntimeResponseBody:
        return await self._run(self._sync.start, project_id, environment_id, **options)

    async def stop(self, project_id: str, environment_id: str, **options: Any) -> StopServiceRuntimeResponseBody:
        return await self._run(self._sync.stop, project_id, environment_id, **options)

    async def restart(self, project_id: str, environment_id: str, **options: Any) -> RestartServiceRuntimeResponseBody:
        return await self._run(self._sync.restart, project_id, environment_id, **options)


def _decode_success(response: Any) -> Any:
    body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("PostGrip Service response is too large")
    return json.loads(body) if body.strip() else None


def _decode_http_error(error: HTTPError, retry_after_max_delay: float) -> ServiceAPIError:
    try:
        body = error.read(_MAX_RESPONSE_BYTES + 1)
    finally:
        error.close()
    try:
        value = json.loads(body) if len(body) <= _MAX_RESPONSE_BYTES else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return ServiceAPIError(
        status=error.code,
        code=value.get("code", "HTTP_ERROR"),
        message=value.get("message", error.reason or "request failed"),
        request_id=value.get("requestId", error.headers.get("X-Request-ID", "")),
        details=value.get("details") if isinstance(value.get("details"), dict) else None,
        retry_after=_parse_retry_after(error.headers.get("Retry-After"), retry_after_max_delay),
    )


def _parse_retry_after(value: str | None, maximum: float) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        if not math.isfinite(seconds):
            return None
        return min(max(seconds, 0.0), maximum)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return min(max((when - datetime.now(timezone.utc)).total_seconds(), 0.0), maximum)
        except (TypeError, ValueError, OverflowError):
            return None


def _jitter(attempt: int, maximum: float) -> float:
    return random.random() * min(0.2 * (2 ** (attempt - 1)), maximum)


def _configured_retry_limits(max_attempts: int, max_delay: float, retry_after_max_delay: float) -> tuple[int, float, float]:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= _MAXIMUM_RETRY_ATTEMPTS:
        raise ValueError(f"retry_max_attempts must be an integer from 1 to {_MAXIMUM_RETRY_ATTEMPTS}")
    if not 0.0 < max_delay <= _MAXIMUM_RETRY_DELAY:
        raise ValueError(f"retry_max_delay must be greater than 0 and at most {_MAXIMUM_RETRY_DELAY}")
    if not 0.0 < retry_after_max_delay <= _MAXIMUM_RETRY_AFTER_DELAY:
        raise ValueError(
            f"retry_after_max_delay must be greater than 0 and at most {_MAXIMUM_RETRY_AFTER_DELAY}"
        )
    return max_attempts, max_delay, retry_after_max_delay
