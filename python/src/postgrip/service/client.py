from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
import os
from threading import Event
import time
from typing import Any, Callable, Literal, cast
from urllib.request import OpenerDirector

from .._internal.config import validate_base_url, validate_idempotency_key, validate_management_token
from .._internal.http import REQUEST_CANCEL_EVENT, RequestCancelled, run_cancellable
from .._internal.transport import APIErrorFields, Executor, PostGripAPIError, RetryConfig, no_redirect_opener
from .._internal.pagination import iterate_pages, iterate_pages_async

from .administration_types import (
    AppsAdministration,
    AsyncAppsAdministration,
    AsyncDeclarativeConfigurationAdministration,
    AsyncDiagnosticsAdministration,
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
    AsyncTrafficAdministration,
    AsyncTargetServicesAdministration,
    AsyncVariablesAdministration,
    ConfigurationOperationsAdministration,
    DeclarativeConfigurationAdministration,
    DiagnosticsAdministration,
    DomainsAdministration,
    DNSAdministration,
    EnvironmentsAdministration,
    ManagedVolumesAdministration,
    ProjectsAdministration,
    PromotionsAdministration,
    RepositoriesAdministration,
    ReleaseGroupsAdministration,
    RetentionAdministration,
    TrafficAdministration,
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

_MAX_SCREENSHOT_RESPONSE_BYTES = 24 << 20
_MAXIMUM_RETRY_ATTEMPTS = 3
_MAXIMUM_RETRY_DELAY = 2.0
_MAXIMUM_RETRY_AFTER_DELAY = 30.0

_ADMINISTRATION_OPERATION_GROUPS: dict[str, tuple[str, ...]] = {
    "apps": (
        "list_service_apps", "get_service_app", "create_service_app",
        "update_service_app", "delete_service_app",
    ),
    "target_services": (
        "attach_target_service", "update_target_service", "get_target_service_removal_impact",
        "detach_target_service", "put_target_service_connection", "clear_target_service_connection",
        "create_managed_target_service", "list_service_postgre_sql_images",
    ),
    "projects": (
        "create_service_project", "update_service_project", "get_service_project_removal_impact",
        "delete_service_project",
    ),
    "environments": (
        "get_service_environment", "create_service_environment", "update_service_environment",
        "preview_service_environment_reassignment", "reassign_service_environment",
        "get_recovery_move", "revise_recovery_move_volume", "confirm_recovery_move_variables",
        "get_service_environment_removal_impact", "delete_service_environment",
        "get_service_compose_file", "put_service_compose_file", "delete_service_compose_file",
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
        "report_service_dns_provider_result",
    ),
    "variables": (
        "list_service_variables", "create_service_variable", "update_service_variable",
        "delete_service_variable", "put_service_variable_value", "clear_service_variable_value",
        "apply_service_variables", "export_service_variables",
    ),
    "repositories": (
        "get_service_repository", "update_service_repository", "put_service_repository_credential",
        "clear_service_repository_credential", "refresh_service_repository_credential",
        "list_git_hub_app_repositories", "preview_git_hub_repository_adoption",
        "adopt_git_hub_repository", "list_service_git_hub_branches",
        "check_service_git_hub_repository_file", "list_service_git_hub_accounts",
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
    "diagnostics": (
        "get_service_deployment_screenshot", "list_service_webhook_dispatch_events",
    ),
    "traffic": (
        "get_service_traffic_status", "get_service_traffic_report", "put_service_traffic_settings",
        "trim_service_traffic", "flush_service_traffic",
    ),
    "configuration_operations": (
        "list_service_configuration_operations", "get_service_configuration_operation",
        "retry_service_configuration_operation", "abandon_service_configuration_operation",
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


@dataclass(frozen=True)
class ServiceAPIError(PostGripAPIError):
    """A failed Service request, with the same fields as before and the shared base."""

    @classmethod
    def _from_fields(cls, fields: APIErrorFields) -> ServiceAPIError:
        return cls(
            status=fields.status,
            code=fields.code,
            message=fields.message,
            request_id=fields.request_id,
            details=fields.details,
            retry_after=fields.retry_after,
        )

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
    """Grouped access to all 105 generated Service-administration operations."""

    apps: AppsAdministration
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
    diagnostics: DiagnosticsAdministration
    traffic: TrafficAdministration
    configuration_operations: ConfigurationOperationsAdministration
    declarative_configuration: DeclarativeConfigurationAdministration

    def __init__(self, transport: Callable[..., Any]) -> None:
        generated = OpenAPIClient(transport)
        self.apps = cast(AppsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["apps"]))
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
        self.diagnostics = cast(DiagnosticsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["diagnostics"]))
        self.traffic = cast(TrafficAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["traffic"]))
        self.configuration_operations = cast(ConfigurationOperationsAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["configuration_operations"]))
        self.declarative_configuration = cast(DeclarativeConfigurationAdministration, _AdministrationGroup(generated, _ADMINISTRATION_OPERATION_GROUPS["declarative_configuration"]))


class AsyncServiceAdministration:
    """Async grouped administration facade backed by the synchronous transport."""

    apps: AsyncAppsAdministration
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
    diagnostics: AsyncDiagnosticsAdministration
    traffic: AsyncTrafficAdministration
    configuration_operations: AsyncConfigurationOperationsAdministration
    declarative_configuration: AsyncDeclarativeConfigurationAdministration

    def __init__(self, client: AsyncServiceClient, sync: ServiceAdministration) -> None:
        self.apps = cast(AsyncAppsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.apps)))
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
        self.diagnostics = cast(AsyncDiagnosticsAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.diagnostics)))
        self.traffic = cast(AsyncTrafficAdministration, _AsyncAdministrationGroup(client, cast(_AdministrationGroup, sync.traffic)))
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
        max_attempts, max_delay, retry_after_max = _configured_retry_limits(
            retry_max_attempts, retry_max_delay, retry_after_max_delay,
        )
        self._follow_interval = max(follow_interval, 0.001)
        self._executor = Executor(
            plane="Service",
            base_url=base_url,
            opener=no_redirect_opener(opener),
            management_token=token,
            retry=RetryConfig(
                enabled=enable_retries, max_attempts=max_attempts, max_delay=max_delay, retry_after_max=retry_after_max,
            ),
            timeout=timeout,
            create_error=ServiceAPIError._from_fields,
            success_response_bytes={OperationId.GET_SERVICE_DEPLOYMENT_SCREENSHOT.value: _MAX_SCREENSHOT_RESPONSE_BYTES},
        )
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
            cancel_token = REQUEST_CANCEL_EVENT.set(cancel)
            try:
                page = self.logs(
                    service, kind=kind, environment_id=environment_id, deployment_id=deployment_id,
                    limit=limit, cursor=cursor, follow=True,
                )
            except RequestCancelled:
                return
            finally:
                REQUEST_CANCEL_EVENT.reset(cancel_token)
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
        # Top-level None values are omitted, so default arguments are not sent as JSON null.
        clean_body = {key: value for key, value in (body or {}).items() if value is not None} if body is not None else None
        operation = resolve_openapi_operation(operation_id, path, clean_query)
        return self._executor.request(operation, body=clean_body, idempotency_key=idempotency_key, if_match=if_match)

    @property
    def _opener(self) -> OpenerDirector:
        return self._executor.opener

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
        return await run_cancellable(callback, *args, **kwargs)

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
