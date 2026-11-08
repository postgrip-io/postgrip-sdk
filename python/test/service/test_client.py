from __future__ import annotations

import asyncio
from email.message import Message
from io import BytesIO
import inspect
import json
from threading import Event
from typing import Literal, get_args, get_type_hints
import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request
from unittest.mock import patch

from _http_fakes import FakeOpener, FakeResponse
from postgrip.service import AsyncServiceClient, ServiceAPIError, ServiceClient, ServiceReference
from postgrip.service.administration_types import (
    ConfigurationOperationsAdministration,
    DeclarativeConfigurationAdministration,
    RepositoriesAdministration,
)
from postgrip._internal.transport import _NoRedirect
from postgrip.service.openapi import (
    OpenAPIPostGripConfigurationSecretVariable,
    OpenAPIServiceReleaseGroupMemberRequest,
    OpenAPIServiceDNSCanonicalTarget,
    OpenAPIServiceDNSPlan,
    OpenAPIServiceAutomaticDeploymentWiring,
    OpenAPICreateManagedTargetServiceRequest,
    OpenAPICreateServiceEnvironmentRequest,
    OpenAPIPostGripConfigurationEnvironment,
    OpenAPIServiceEnvironmentPlacement,
    OpenAPIServiceOperationResponse,
    OpenAPIServiceTarget,
    OpenAPITargetServiceConnectionRequest,
    OpenAPITargetServiceHTTPCredential,
    OperationId,
)


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


class AdministrationTypeTests(unittest.TestCase):
    def test_repository_wiring_status_is_closed(self) -> None:
        hints = get_type_hints(OpenAPIServiceAutomaticDeploymentWiring)
        self.assertEqual(
            hints["status"],
            Literal[
                "pending",
                "active",
                "disabled",
                "provider-unsupported",
                "base-url-not-public",
                "no-worker-assigned",
                "registration-failed",
            ],
        )

    def test_environment_placement_is_server_resolvable_and_closed(self) -> None:
        self.assertNotIn("assignedWorkerId", OpenAPICreateServiceEnvironmentRequest.__required_keys__)
        self.assertNotIn("assignedWorker", OpenAPIPostGripConfigurationEnvironment.__required_keys__)
        hints = get_type_hints(OpenAPIServiceEnvironmentPlacement)
        self.assertEqual(
            hints["mode"],
            Literal["automatic", "project-default", "explicit", "reassigned", "legacy"],
        )

    def test_runtime_type_hints_resolve_closed_literals(self) -> None:
        get_type_hints(RepositoriesAdministration.put_service_repository_credential)
        get_type_hints(ConfigurationOperationsAdministration.list_service_configuration_operations)
        get_type_hints(DeclarativeConfigurationAdministration.create_post_grip_configuration_plan)

    def test_const_true_field_remains_literal_true(self) -> None:
        hints = get_type_hints(OpenAPIPostGripConfigurationSecretVariable)
        self.assertEqual(hints["isSecret"], Literal[True])

    def test_dns_operation_names_keep_the_acronym_intact(self) -> None:
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=FakeOpener([]))  # type: ignore[arg-type]
        self.assertTrue(hasattr(client.administration.dns, "get_service_dns_plan"))
        self.assertFalse(hasattr(client.administration.dns, "get_service_d_n_s_plan"))

    def test_dns_response_types_preserve_server_guarantees(self) -> None:
        plan_hints = get_type_hints(OpenAPIServiceDNSPlan)
        target_hints = get_type_hints(OpenAPIServiceDNSCanonicalTarget)
        self.assertEqual(plan_hints["providerMode"], Literal["external"])
        self.assertIn("workerId", target_hints)

    def test_release_members_preserve_revision_source_alternatives(self) -> None:
        alternatives = get_args(OpenAPIServiceReleaseGroupMemberRequest)
        self.assertEqual(len(alternatives), 2)
        required = [value.__required_keys__ for value in alternatives]
        self.assertIn(frozenset({"key", "projectId", "environmentId", "expectedCommitSha", "branch"}), required)
        self.assertIn(frozenset({"key", "projectId", "environmentId", "sourceDeploymentId", "expectedArtifactIdentity"}), required)


def api_error(status: int, code: str = "BUSY", retry_after: str = "0") -> HTTPError:
    headers = Message()
    headers["Retry-After"] = retry_after
    body = BytesIO(json.dumps({"code": code, "message": "try later", "requestId": "req-1"}).encode())
    return HTTPError("https://services.example.test", status, "failed", headers, body)


class ServiceClientTests(unittest.TestCase):
    @staticmethod
    def _administration_arguments(method: object) -> tuple[list[object], dict[str, object]]:
        positional: list[object] = []
        keywords: dict[str, object] = {}
        for parameter in inspect.signature(method).parameters.values():
            if parameter.default is not inspect.Parameter.empty:
                continue
            if parameter.name == "body":
                value: object = {}
            elif parameter.name == "credential_kind":
                value = "source-access"
            elif parameter.name == "idempotency_key":
                value = "operation-1"
            elif parameter.name == "if_match":
                value = '"etag:1"'
            else:
                value = f"{parameter.name.replace('_', '-')}-value"
            if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                keywords[parameter.name] = value
            else:
                positional.append(value)
        return positional, keywords

    def test_list_injects_bearer_and_terminal_query_names(self) -> None:
        opener = FakeOpener([{"items": [SERVICE], "nextCursor": ""}])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        page = client.list(kind="backend", worker_id="worker-id", limit=25)
        self.assertEqual(page["items"][0]["name"], "api")
        request = opener.requests[0]
        self.assertIn("kind=backend", request.full_url)
        self.assertIn("worker=worker-id", request.full_url)
        self.assertNotIn("worker_id", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer pgt_test-token")

    def test_resolve_and_scoped_status(self) -> None:
        opener = FakeOpener([SERVICE, {"service": SERVICE, "environments": []}])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        service = client.resolve("api")
        status = client.for_service(service).status()
        self.assertEqual(status["service"]["ref"], SERVICE["ref"])
        self.assertIn(f"/api/v1/services/project/{SERVICE['id']}/status", opener.requests[1].full_url)

    def test_service_references_validate_mapping_and_explicit_values(self) -> None:
        reference = ServiceReference.from_service(SERVICE)
        self.assertEqual(reference.path(), {"source": "project", "serviceId": SERVICE["id"]})
        for invalid in ({}, {"source": "external", "id": "service-id"}, {"source": "project", "id": ""}):
            with self.assertRaises(ValueError):
                ServiceReference.from_service(invalid)
        with self.assertRaises(ValueError):
            ServiceReference("project", "").path()

    def test_deploy_sends_json_and_idempotency_key(self) -> None:
        response = {
            "status": "queued", "serviceRef": SERVICE["ref"], "environmentId": "environment-id",
            "deploymentId": "deployment-id", "deployment": {},
            "receipt": {"requestId": "request-id", "auditRecorded": True, "replayed": False},
        }
        opener = FakeOpener([response])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
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
            base_url="https://services.example.test", token="pgt_test-token",
            opener=opener, enable_retries=True,
        )  # type: ignore[arg-type]
        with patch("postgrip.service.client.time.sleep"):
            self.assertEqual(client.cancel("project", "deployment", idempotency_key="cancel-1")["status"], "cancelled")
        self.assertEqual(len(opener.requests), 3)

    def test_invalid_idempotency_key_fails_before_request(self) -> None:
        opener = FakeOpener([])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            client.cancel("project", "deployment", idempotency_key="contains space")
        self.assertEqual(opener.requests, [])

    def test_pages_use_opaque_cursor(self) -> None:
        opener = FakeOpener([
            {"items": [], "nextCursor": "next"},
            {"items": [], "nextCursor": ""},
        ])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        self.assertEqual([page["nextCursor"] for page in client.pages()], ["next", ""])
        self.assertNotIn("cursor=", opener.requests[0].full_url)
        self.assertIn("cursor=next", opener.requests[1].full_url)

    def test_environment_and_deployment_pages_use_opaque_cursors(self) -> None:
        opener = FakeOpener([
            {"items": [], "nextCursor": "environment-next"},
            {"items": [], "nextCursor": ""},
            {"items": [], "nextCursor": "deployment-next"},
            {"items": [], "nextCursor": ""},
        ])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        reference = ServiceReference("project", "project-id")
        self.assertEqual(
            [page["nextCursor"] for page in client.environment_pages(reference, limit=1)],
            ["environment-next", ""],
        )
        self.assertEqual(
            [page["nextCursor"] for page in client.deployment_pages(reference, limit=1)],
            ["deployment-next", ""],
        )
        self.assertIn("cursor=environment-next", opener.requests[1].full_url)
        self.assertIn("cursor=deployment-next", opener.requests[3].full_url)

    def test_follow_uses_cursor_and_stops_after_cancel(self) -> None:
        opener = FakeOpener([
            {"items": [{"kind": "runtime", "message": "one"}, {"kind": "runtime", "message": "two"}], "nextCursor": "next", "pollAfterMs": 1},
        ])
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
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
            base_url="https://services.example.test", token="pgt_test-token",
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
        client = ServiceClient(base_url="https://services.example.test", token="pgt_test-token", opener=opener)  # type: ignore[arg-type]
        with self.assertRaises(ServiceAPIError) as raised:
            client.resolve("api")
        self.assertEqual(raised.exception.code, "HTTP_ERROR")
        self.assertEqual(raised.exception.request_id, "request-header")
        self.assertNotIn("secret", str(raised.exception))

    def test_requires_https_and_non_empty_opaque_management_token(self) -> None:
        with self.assertRaises(ValueError):
            ServiceClient(base_url="http://example.test", token="pgt_token")
        with self.assertRaises(ValueError):
            ServiceClient(base_url="https://example.test", token="   ")
        self.assertIsInstance(
            ServiceClient(base_url="https://example.test", token="opaque-token"),
            ServiceClient,
        )
        for base_url in ("https://example.test?", "https://example.test#"):
            with self.assertRaises(ValueError):
                ServiceClient(base_url=base_url, token="pgt_token")
        with self.assertRaises(ValueError):
            ServiceClient(base_url="https://example.test", token="pgt_token", retry_max_attempts=4)

    def test_loads_documented_service_environment_variables(self) -> None:
        client = ServiceClient.from_env(environ={
            "POSTGRIP_SERVICE_URL": "https://services.example.test",
            "POSTGRIP_TOKEN": "pgt_environment-token",
        })
        self.assertIsInstance(client, ServiceClient)

    def test_retries_are_disabled_by_default(self) -> None:
        opener = FakeOpener([api_error(503)])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaises(ServiceAPIError):
            client.resolve("api")
        self.assertEqual(len(opener.requests), 1)

    def test_retry_configuration_caps_attempts_and_retry_after(self) -> None:
        opener = FakeOpener([api_error(503, retry_after="30"), api_error(503, retry_after="30")])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            enable_retries=True, retry_max_attempts=2, retry_after_max_delay=0.001,
        )  # type: ignore[arg-type]
        with patch("postgrip.service.client.time.sleep") as sleep:
            with self.assertRaises(ServiceAPIError) as raised:
                client.resolve("api")
        sleep.assert_called_once_with(0.001)
        self.assertEqual(raised.exception.retry_after, 0.001)
        self.assertEqual(len(opener.requests), 2)

    def test_safe_release_preview_post_retries_without_idempotency_key(self) -> None:
        opener = FakeOpener([api_error(503), {}])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            enable_retries=True, retry_max_attempts=2,
        )  # type: ignore[arg-type]
        body = {
            "name": "release",
            "members": [
                {"key": "api", "projectId": "project-1", "environmentId": "environment-1", "expectedCommitSha": "abc1234", "branch": "main"},
                {"key": "web", "projectId": "project-2", "environmentId": "environment-2", "expectedCommitSha": "abc1234", "branch": "main"},
            ],
        }
        with patch("postgrip.service.client.time.sleep"):
            client.administration.release_groups.preview_service_release_group(body)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0].method, "POST")
        self.assertIsNone(opener.requests[0].get_header("Idempotency-key"))

    def test_non_finite_retry_after_uses_jitter(self) -> None:
        opener = FakeOpener([api_error(503, retry_after="NaN"), SERVICE])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            enable_retries=True,
        )  # type: ignore[arg-type]
        with patch("postgrip._internal.transport.jitter", return_value=0.125):
            with patch("postgrip.service.client.time.sleep") as sleep:
                self.assertEqual(client.resolve("api")["id"], SERVICE["id"])
        sleep.assert_called_once_with(0.125)
        self.assertEqual(len(opener.requests), 2)

    def test_oversized_http_error_body_is_closed(self) -> None:
        headers = Message()
        body = BytesIO(b"x" * ((4 << 20) + 1))
        error = HTTPError("https://services.example.test", 502, "failed", headers, body)
        opener = FakeOpener([error])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaises(ServiceAPIError):
            client.resolve("api")
        self.assertTrue(body.closed)

    def test_response_body_limit(self) -> None:
        opener = FakeOpener([b"x" * ((4 << 20) + 1)])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "too large"):
            client.resolve("api")

    def test_screenshot_uses_schema_sized_response_limit(self) -> None:
        data = "A" * ((4 << 20) + 4)
        opener = FakeOpener([{"contentType": "image/png", "dataBase64": data}])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]

        response = client.administration.diagnostics.get_service_deployment_screenshot(
            "project-id", "deployment-id",
        )
        self.assertEqual(response["dataBase64"], data)

    def test_redirect_handler_never_constructs_a_forwarded_request(self) -> None:
        request = Request("https://services.example.test/api/v1/services", headers={
            "Authorization": "Bearer pgt_test-token",
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
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
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

    def test_administration_facade_covers_every_additive_operation_and_fences_writes(self) -> None:
        response = {
            "target": {}, "operation": {},
            "receipt": {"requestId": "request-id", "auditRecorded": True, "replayed": False},
        }
        opener = FakeOpener([response])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        groups = (
            client.administration.apps,
            client.administration.target_services,
            client.administration.projects,
            client.administration.environments,
            client.administration.managed_volumes,
            client.administration.domains,
            client.administration.dns,
            client.administration.variables,
            client.administration.repositories,
            client.administration.promotions,
            client.administration.release_groups,
            client.administration.retention,
            client.administration.diagnostics,
            client.administration.traffic,
            client.administration.configuration_operations,
            client.administration.declarative_configuration,
        )
        exposed = {name for group in groups for name in dir(group)}
        phase_seven = {
            "list_services", "resolve_service", "get_service", "get_service_status",
            "list_service_environments", "resolve_service_environment", "list_service_deployments",
            "get_service_deployment", "list_service_logs", "check_service", "preview_service_deploy",
            "deploy_service", "redeploy_service", "cancel_service_deployment",
            "rollback_service_deployment", "start_service_runtime", "stop_service_runtime",
            "restart_service_runtime",
        }
        canonical = {operation.name.lower() for operation in OperationId} - phase_seven
        self.assertEqual(exposed, canonical)
        self.assertEqual(len(exposed), 108)

        client.administration.target_services.attach_target_service(
            {
                "workerId": "worker-id", "name": "database", "slug": "database",
                "host": "database.internal", "port": 5432, "databaseName": "app",
                "metadata": {},
            },
            idempotency_key="attach-1",
            if_match='"service-catalog:4"',
        )
        request = opener.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(urlparse(request.full_url).path, "/api/v1/services/targets")
        self.assertEqual(request.get_header("Idempotency-key"), "attach-1")
        self.assertEqual(request.get_header("If-match"), '"service-catalog:4"')

    def test_create_managed_target_service_sends_both_fences_and_no_password(self) -> None:
        self.assertNotIn("password", get_type_hints(OpenAPICreateManagedTargetServiceRequest))
        self.assertEqual(
            get_type_hints(OpenAPICreateManagedTargetServiceRequest)["kind"],
            Literal["postgresql", "sqlite"],
        )
        created = {
            "target": {"id": "target-1", "managed": True},
            "configurationRevision": 2,
            "receipt": {"requestId": "request-1", "auditRecorded": True, "replayed": False},
        }
        catalog = {"source": "official", "fetchedAt": "2026-11-08T00:00:00Z", "images": [{"image": "postgres:17.6-bookworm"}]}
        opener = FakeOpener([created, catalog])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        targets = client.administration.target_services

        response = targets.create_managed_target_service(
            {
                "kind": "postgresql", "workerId": "worker-1", "name": "db", "slug": "db",
                "volumeName": "db-data", "imageRef": "postgres:17.6-bookworm",
            },
            idempotency_key="managed-1", if_match='"service-catalog:4"',
        )
        images = targets.list_service_postgre_sql_images(worker_id="worker-1")

        self.assertEqual(response["target"]["id"], "target-1")
        self.assertEqual(response["configurationRevision"], 2)
        self.assertEqual(images["images"][0]["image"], "postgres:17.6-bookworm")
        create, listing = opener.requests
        self.assertEqual(create.method, "POST")
        self.assertEqual(urlparse(create.full_url).path, "/api/v1/services/targets/managed")
        self.assertEqual(create.get_header("Idempotency-key"), "managed-1")
        self.assertEqual(create.get_header("If-match"), '"service-catalog:4"')
        self.assertEqual(json.loads(create.data), {
            "kind": "postgresql", "workerId": "worker-1", "name": "db", "slug": "db",
            "volumeName": "db-data", "imageRef": "postgres:17.6-bookworm",
        })
        self.assertEqual(listing.method, "GET")
        self.assertEqual(urlparse(listing.full_url).path, "/api/v1/services/postgresql-images")
        self.assertEqual(urlparse(listing.full_url).query, "workerId=worker-1")
        self.assertIsNone(listing.get_header("If-match"))

    def test_put_target_service_connection_sends_the_http_credential_as_given(self) -> None:
        self.assertEqual(OpenAPITargetServiceConnectionRequest.__required_keys__, frozenset())
        self.assertEqual(
            get_type_hints(OpenAPITargetServiceHTTPCredential)["scheme"],
            Literal["none", "basic", "bearer", "api_key"],
        )
        self.assertIn("httpAuth", get_type_hints(OpenAPIServiceTarget))
        self.assertIn("httpStatus", get_type_hints(OpenAPIServiceOperationResponse))
        answer = {"target": {"httpAuth": {"scheme": "bearer"}}}
        opener = FakeOpener([answer, answer])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        targets = client.administration.target_services

        response = targets.put_target_service_connection(
            "target-1", {"http": {"scheme": "bearer", "token": "token-value"}},
            idempotency_key="connection-1", if_match='"target:3"',
        )
        targets.put_target_service_connection(
            "target-1", {"password": "database-secret"},
            idempotency_key="connection-1", if_match='"target:3"',
        )

        self.assertEqual(response["target"]["httpAuth"], {"scheme": "bearer"})
        for request in opener.requests:
            self.assertEqual(request.method, "PUT")
            self.assertEqual(urlparse(request.full_url).path, "/api/v1/services/target/target-1/connection")
            self.assertEqual(request.get_header("Idempotency-key"), "connection-1")
            self.assertEqual(request.get_header("If-match"), '"target:3"')
        self.assertEqual(
            [json.loads(request.data) for request in opener.requests],
            [{"http": {"scheme": "bearer", "token": "token-value"}}, {"password": "database-secret"}],
        )

    def test_apps_list_exposes_catalog_fence(self) -> None:
        opener = FakeOpener([{
            "items": [],
            "catalogVersion": 7,
            "catalogEtag": '"service-catalog:7"',
        }])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]

        response = client.administration.apps.list_service_apps()

        self.assertEqual(response["catalogVersion"], 7)
        self.assertEqual(response["catalogEtag"], '"service-catalog:7"')

    def test_every_administration_facade_executes_through_the_transport(self) -> None:
        opener = FakeOpener([{} for _ in range(102)])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        groups = (
            client.administration.apps,
            client.administration.target_services,
            client.administration.projects,
            client.administration.environments,
            client.administration.managed_volumes,
            client.administration.domains,
            client.administration.dns,
            client.administration.variables,
            client.administration.repositories,
            client.administration.promotions,
            client.administration.retention,
            client.administration.diagnostics,
            client.administration.traffic,
            client.administration.configuration_operations,
            client.administration.declarative_configuration,
        )

        for group in groups:
            for name in dir(group):
                method = getattr(group, name)
                positional, keywords = self._administration_arguments(method)
                method(*positional, **keywords)

        self.assertEqual(len(opener.requests), 101)
        self.assertTrue(all(
            request.get_header("Authorization") == "Bearer pgt_test-token"
            for request in opener.requests
        ))
        mutations = [
            request for request in opener.requests
            if request.method != "GET"
            and urlparse(request.full_url).path != "/api/v1/services/configuration/validate"
        ]
        self.assertTrue(mutations)
        self.assertTrue(all(
            request.get_header("Idempotency-key") == "operation-1"
            for request in mutations
        ))
        with self.assertRaises(AttributeError):
            getattr(client.administration.projects, "unsupported_operation")

    def test_bulk_variable_apply_uses_per_environment_fences_without_if_match(self) -> None:
        opener = FakeOpener([{
            "results": [],
            "receipt": {"requestId": "request-id", "auditRecorded": True, "replayed": False},
        }])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]

        client.administration.variables.apply_service_variables(
            "project-id",
            {"changes": [{
                "environmentId": "environment-id",
                "name": "DATABASE_URL",
                "isSecret": True,
                "value": "postgres://example",
                "expectedCollectionVersion": 7,
            }]},
            idempotency_key="apply-1",
        )

        request = opener.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(urlparse(request.full_url).path, "/api/v1/services/project/project-id/variables/apply")
        self.assertEqual(request.get_header("Idempotency-key"), "apply-1")
        self.assertIsNone(request.get_header("If-match"))

    def test_administration_rejects_invalid_fences_before_fetching(self) -> None:
        opener = FakeOpener([])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            client.administration.configuration_operations.retry_service_configuration_operation(
                "operation-id", idempotency_key="contains space", if_match='"operation:1"',
            )
        with self.assertRaises(ValueError):
            client.administration.configuration_operations.retry_service_configuration_operation(
                "operation-id", idempotency_key="retry-1", if_match="bad\r\netag",
            )
        self.assertEqual(opener.requests, [])

    def test_scoped_facade_covers_reads_logs_and_health_check(self) -> None:
        opener = FakeOpener([
            {}, {}, {}, {}, {},
            {"items": [{"message": "one"}, {"message": "two"}], "nextCursor": "next"},
            {},
        ])
        client = ServiceClient(
            base_url="https://services.example.test", token="pgt_test-token", opener=opener,
        )  # type: ignore[arg-type]
        scoped = client.for_service(ServiceReference("project", "project-id"))
        scoped.get()
        scoped.status(environment="production")
        scoped.environments(limit=10)
        scoped.deployments(limit=10)
        scoped.logs(kind="runtime")
        cancel = Event()
        iterator = scoped.follow_logs(cancel=cancel)
        self.assertEqual(next(iterator)["message"], "one")
        cancel.set()
        with self.assertRaises(StopIteration):
            next(iterator)
        scoped.check(idempotency_key="operation-1")
        self.assertEqual(len(opener.requests), 7)

    def test_async_pages(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [], "nextCursor": "next"},
                {"items": [], "nextCursor": ""},
            ])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            )  # type: ignore[arg-type]
            cursors = [page["nextCursor"] async for page in client.pages()]
            self.assertEqual(cursors, ["next", ""])

        asyncio.run(run())

    def test_async_client_loads_documented_environment_variables(self) -> None:
        client = AsyncServiceClient.from_env(environ={
            "POSTGRIP_SERVICE_URL": "https://services.example.test",
            "POSTGRIP_TOKEN": "pgt_environment-token",
        })
        self.assertIsInstance(client, AsyncServiceClient)

    def test_async_runtime_facades_execute_sync_transport(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [], "nextCursor": "next"},
                {"items": [], "nextCursor": ""},
                *[{} for _ in range(17)],
            ])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            )  # type: ignore[arg-type]
            reference = ServiceReference("project", "project-id")

            self.assertEqual(
                [page["nextCursor"] async for page in client.pages(limit=1)],
                ["next", ""],
            )
            await client.resolve("api")
            await client.get(reference)
            await client.status(reference, environment="production")
            await client.environments(reference, limit=10)
            await client.environment("project-id", "production")
            await client.deployments(reference, limit=10)
            await client.deployment("project-id", "deployment-id")
            await client.logs(reference, kind="runtime")
            await client.check(reference, idempotency_key="operation-1")
            await client.preview_deploy("project-id", environment="production")
            await client.deploy(
                "project-id", expected_commit_sha="commit", idempotency_key="operation-1",
            )
            await client.redeploy("project-id", idempotency_key="operation-1")
            await client.cancel("project-id", "deployment-id", idempotency_key="operation-1")
            await client.rollback("project-id", "deployment-id", idempotency_key="operation-1")
            await client.start(
                "project-id", "environment-id",
                expected_deployment_id="deployment-id", idempotency_key="operation-1",
            )
            await client.stop(
                "project-id", "environment-id",
                expected_deployment_id="deployment-id", idempotency_key="operation-1",
            )
            await client.restart(
                "project-id", "environment-id",
                expected_deployment_id="deployment-id", idempotency_key="operation-1",
            )
            self.assertEqual(len(opener.requests), 19)

        asyncio.run(run())

    def test_async_administration_facades_execute_through_the_transport(self) -> None:
        async def run() -> None:
            opener = FakeOpener([{} for _ in range(102)])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgt_test-token", opener=opener,
            )  # type: ignore[arg-type]
            groups = (
                (client.administration.apps, client._sync.administration.apps),
                (client.administration.target_services, client._sync.administration.target_services),
                (client.administration.projects, client._sync.administration.projects),
                (client.administration.environments, client._sync.administration.environments),
                (client.administration.managed_volumes, client._sync.administration.managed_volumes),
                (client.administration.domains, client._sync.administration.domains),
                (client.administration.dns, client._sync.administration.dns),
                (client.administration.variables, client._sync.administration.variables),
                (client.administration.repositories, client._sync.administration.repositories),
                (client.administration.promotions, client._sync.administration.promotions),
                (client.administration.retention, client._sync.administration.retention),
                (client.administration.diagnostics, client._sync.administration.diagnostics),
                (client.administration.traffic, client._sync.administration.traffic),
                (
                    client.administration.configuration_operations,
                    client._sync.administration.configuration_operations,
                ),
                (
                    client.administration.declarative_configuration,
                    client._sync.administration.declarative_configuration,
                ),
            )

            for async_group, sync_group in groups:
                for name in dir(async_group):
                    positional, keywords = self._administration_arguments(getattr(sync_group, name))
                    await getattr(async_group, name)(*positional, **keywords)

            self.assertEqual(len(opener.requests), 101)

        asyncio.run(run())

    def test_async_log_follower_uses_cursor_and_server_delay(self) -> None:
        async def run() -> None:
            opener = FakeOpener([
                {"items": [{"message": "one"}], "nextCursor": "next", "pollAfterMs": 0},
                {"items": [], "nextCursor": "later", "pollAfterMs": 1},
            ])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgt_test-token", opener=opener,
                follow_interval=0.001,
            )  # type: ignore[arg-type]
            iterator = client.follow_logs(ServiceReference("project", "project-id"))
            self.assertEqual((await anext(iterator))["message"], "one")
            pending = asyncio.create_task(anext(iterator))
            while len(opener.requests) < 2:
                await asyncio.sleep(0)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            await iterator.aclose()
            self.assertIn("cursor=next", opener.requests[1].full_url)

        asyncio.run(run())

    def test_async_cancellation_interrupts_retry_backoff(self) -> None:
        async def run() -> None:
            opener = FakeOpener([api_error(503, retry_after="30")])
            client = AsyncServiceClient(
                base_url="https://services.example.test", token="pgt_test-token",
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
