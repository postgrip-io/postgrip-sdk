#!/usr/bin/env python3
"""Run contract-owned live API scenarios with disposable-resource safeguards.

The checked-in operation ownership file decides cadence. Environment-specific
scenario data supplies valid repository, worker, image, and host-runtime
fixtures without committing credentials or durable identifiers to this repo.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import sys
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Timer
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "test" / "operation-inventory.json"
OWNERSHIP_PATH = ROOT / "test" / "operation-tests.json"
TIERS = ("nightly", "pre-release", "production-smoke")
PRODUCTION_ALLOWLIST = frozenset({"health", "workerOrchestratorHealth"})
PLACEHOLDER = re.compile(
    r"\$\{(runPrefix|runId|var\.[A-Za-z][A-Za-z0-9_]*|env\.POSTGRIP_[A-Z0-9_]+)\}"
)
NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class LiveSuiteError(RuntimeError):
    """A safe, redacted live-suite failure."""


class OperationAdapter(Protocol):
    def execute(
        self, operation: Mapping[str, Any], request: Mapping[str, Any]
    ) -> Any: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveSuiteError(f"could not load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LiveSuiteError(f"{path} must contain a JSON object")
    return value


def load_scenario(path: Path | None, environ: Mapping[str, str]) -> dict[str, Any]:
    if path is not None:
        return load_json(path)
    compressed = environ.get("POSTGRIP_LIVE_SCENARIO_GZIP_BASE64", "").strip()
    raw = environ.get("POSTGRIP_LIVE_SCENARIO_JSON", "").strip()
    if bool(compressed) == bool(raw):
        raise LiveSuiteError(
            "provide exactly one of --scenario, POSTGRIP_LIVE_SCENARIO_JSON, or "
            "POSTGRIP_LIVE_SCENARIO_GZIP_BASE64"
        )
    try:
        text = (
            gzip.decompress(base64.b64decode(compressed, validate=True)).decode()
            if compressed
            else raw
        )
        value = json.loads(text)
    except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveSuiteError(
            "the live scenario secret is not valid JSON/gzip-base64"
        ) from exc
    if not isinstance(value, dict):
        raise LiveSuiteError("the live scenario must contain a JSON object")
    return value


def resolve_template(
    value: Any,
    variables: Mapping[str, Any],
    environ: Mapping[str, str],
    run_id: str,
    run_prefix: str,
) -> Any:
    if isinstance(value, list):
        return [
            resolve_template(item, variables, environ, run_id, run_prefix)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: resolve_template(item, variables, environ, run_id, run_prefix)
            for key, item in value.items()
        }
    if not isinstance(value, str):
        return value

    def lookup(name: str) -> Any:
        if name == "runPrefix":
            return run_prefix
        if name == "runId":
            return run_id
        if name.startswith("var."):
            key = name[4:]
            if key not in variables:
                raise LiveSuiteError(f"scenario references unavailable capture {key!r}")
            return variables[key]
        key = name[4:]
        resolved = environ.get(key)
        if resolved is None or not resolved.strip():
            raise LiveSuiteError(f"scenario requires environment value {key}")
        return resolved

    full = PLACEHOLDER.fullmatch(value)
    if full:
        return lookup(full.group(1))

    def replace(match: re.Match[str]) -> str:
        return str(lookup(match.group(1)))

    resolved = PLACEHOLDER.sub(replace, value)
    if "${" in resolved:
        raise LiveSuiteError(
            "scenario contains an unsupported or unresolved placeholder"
        )
    return resolved


def json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise LiveSuiteError(f"capture pointer {pointer!r} must start with '/'")
    current = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise LiveSuiteError(
                    f"capture pointer {pointer!r} did not resolve"
                ) from exc
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise LiveSuiteError(f"capture pointer {pointer!r} did not resolve")
    return current


def contains_scalar(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return any(contains_scalar(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(contains_scalar(item, expected) for item in value)
    return str(value) == expected


def validate_request(value: Any, location: str) -> dict[str, Any]:
    expected = {"pathParameters", "query", "headers", "body", "streamBodyBase64"}
    if not isinstance(value, dict) or set(value) != expected:
        raise LiveSuiteError(f"{location} must contain exactly {sorted(expected)}")
    if not all(
        isinstance(value[name], dict) for name in ("pathParameters", "query", "headers")
    ):
        raise LiveSuiteError(
            f"{location} pathParameters, query, and headers must be objects"
        )
    stream = value["streamBodyBase64"]
    if stream is not None and not isinstance(stream, str):
        raise LiveSuiteError(f"{location}.streamBodyBase64 must be a string or null")
    return value


def validate_cleanup(
    value: Any, location: str, operations: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"operationId", "request"}:
        raise LiveSuiteError(f"{location} must contain operationId and request")
    operation_id = value["operationId"]
    if operation_id not in operations:
        raise LiveSuiteError(
            f"{location} references unknown operation {operation_id!r}"
        )
    validate_request(value["request"], f"{location}.request")
    return value


def validate_resource(
    value: Any, location: str, operations: Mapping[str, Any], *, seeded: bool
) -> dict[str, Any]:
    required = {"key", "kind", "identifier", "name", "cleanup"}
    if not isinstance(value, dict) or set(value) != required:
        raise LiveSuiteError(f"{location} must contain exactly {sorted(required)}")
    for name in ("key", "kind", "identifier", "name"):
        if not isinstance(value[name], str) or not value[name]:
            raise LiveSuiteError(f"{location}.{name} must be a non-empty string")
    validate_cleanup(value["cleanup"], f"{location}.cleanup", operations)
    if seeded and "${runPrefix}" not in value["name"]:
        raise LiveSuiteError(f"{location}.name must contain ${{runPrefix}}")
    return value


def validate_scenario(
    scenario: dict[str, Any],
    *,
    tier: str,
    inventory: Mapping[str, Any],
    ownership: Mapping[str, Any],
) -> None:
    required = {
        "schemaVersion",
        "contractBundleDigest",
        "tier",
        "disposableEnvironment",
        "seedResources",
        "steps",
    }
    if set(scenario) != required or scenario.get("schemaVersion") != 1:
        raise LiveSuiteError(f"scenario root must contain exactly {sorted(required)}")
    if scenario["tier"] != tier:
        raise LiveSuiteError(
            f"scenario tier {scenario['tier']!r} does not match requested tier {tier!r}"
        )
    if scenario["contractBundleDigest"] != inventory["contractBundleDigest"]:
        raise LiveSuiteError("scenario contract bundle differs from generated clients")
    if not isinstance(scenario["disposableEnvironment"], bool):
        raise LiveSuiteError("scenario disposableEnvironment must be boolean")
    operations = {row["operationId"]: row for row in inventory["operations"]}
    seeds = scenario["seedResources"]
    steps = scenario["steps"]
    if not isinstance(seeds, list) or not isinstance(steps, list):
        raise LiveSuiteError("scenario seedResources and steps must be arrays")
    keys: set[str] = set()
    for index, resource in enumerate(seeds):
        validated = validate_resource(
            resource, f"seedResources[{index}]", operations, seeded=True
        )
        if validated["key"] in keys:
            raise LiveSuiteError(f"duplicate resource key {validated['key']!r}")
        keys.add(validated["key"])
    actual_ids: list[str] = []
    for index, step in enumerate(steps):
        location = f"steps[{index}]"
        required_step = {
            "operationId",
            "request",
            "capture",
            "resourceKey",
            "createsResource",
            "cleansResources",
        }
        if not isinstance(step, dict) or set(step) != required_step:
            raise LiveSuiteError(
                f"{location} must contain exactly {sorted(required_step)}"
            )
        operation_id = step["operationId"]
        if operation_id not in operations:
            raise LiveSuiteError(
                f"{location} references unknown operation {operation_id!r}"
            )
        actual_ids.append(operation_id)
        validate_request(step["request"], f"{location}.request")
        capture = step["capture"]
        if not isinstance(capture, dict) or not all(
            isinstance(name, str) and name and isinstance(pointer, str)
            for name, pointer in capture.items()
        ):
            raise LiveSuiteError(f"{location}.capture must map names to JSON pointers")
        resource_key = step["resourceKey"]
        if resource_key is not None and (
            not isinstance(resource_key, str) or not resource_key
        ):
            raise LiveSuiteError(f"{location}.resourceKey must be a string or null")
        creates = step["createsResource"]
        if creates is not None:
            validated = validate_resource(
                creates, f"{location}.createsResource", operations, seeded=False
            )
            if validated["key"] in keys:
                raise LiveSuiteError(f"duplicate resource key {validated['key']!r}")
            keys.add(validated["key"])
        cleaned = step["cleansResources"]
        if not isinstance(cleaned, list) or not all(
            isinstance(key, str) and key for key in cleaned
        ):
            raise LiveSuiteError(
                f"{location}.cleansResources must be an array of resource keys"
            )

    expected_ids = {
        operation_id
        for operation_id, owner in ownership.items()
        if owner["liveTest"] == tier
    }
    if len(actual_ids) != len(set(actual_ids)):
        duplicates = sorted({item for item in actual_ids if actual_ids.count(item) > 1})
        raise LiveSuiteError(f"scenario repeats operations: {duplicates}")
    if set(actual_ids) != expected_ids:
        raise LiveSuiteError(
            f"scenario operation ownership differs: missing={sorted(expected_ids - set(actual_ids))}, "
            f"extra={sorted(set(actual_ids) - expected_ids)}"
        )
    if tier == "production-smoke":
        if expected_ids != PRODUCTION_ALLOWLIST:
            raise LiveSuiteError(
                "production ownership differs from the hard-coded smoke allowlist"
            )
        for operation_id in expected_ids:
            operation = operations[operation_id]
            if operation["safety"] != "read-only" or operation["authLane"] != "public":
                raise LiveSuiteError(
                    f"production smoke operation {operation_id} is not public/read-only"
                )


@dataclass
class ResourceRecord:
    key: str
    kind: str
    identifier: str
    name: str
    cleanup: dict[str, Any] = field(repr=False)
    cleaned: bool = False
    cleanup_error: str | None = None


@dataclass
class OperationRecord:
    operation_id: str
    plane: str
    status: str
    completed_at: str


class CleanupLedger:
    def __init__(
        self, path: Path, *, tier: str, run_id: str, run_prefix: str, digest: str
    ) -> None:
        self.path = path
        self.tier = tier
        self.run_id = run_id
        self.run_prefix = run_prefix
        self.digest = digest
        self.started_at = utc_now()
        self.finished_at: str | None = None
        self.status = "running"
        self.primary_failure: str | None = None
        self.operations: list[OperationRecord] = []
        self.resources: list[ResourceRecord] = []
        self.write()

    def payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "contractBundleDigest": self.digest,
            "tier": self.tier,
            "runId": self.run_id,
            "runPrefix": self.run_prefix,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "status": self.status,
            "primaryFailure": self.primary_failure,
            "operations": [asdict(item) for item in self.operations],
            "resources": [
                {
                    "key": item.key,
                    "kind": item.kind,
                    "identifier": item.identifier,
                    "name": item.name,
                    "cleaned": item.cleaned,
                    "cleanupError": item.cleanup_error,
                }
                for item in self.resources
            ],
            "remainingIdentifiers": [
                item.identifier for item in self.resources if not item.cleaned
            ],
        }

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(self.payload(), indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class FixtureManager:
    def __init__(
        self,
        *,
        scenario: dict[str, Any],
        inventory: dict[str, Any],
        ownership: dict[str, Any],
        tier: str,
        adapter: OperationAdapter,
        environ: Mapping[str, str],
        ledger_path: Path,
        allow_destructive: bool,
        run_id: str | None = None,
    ) -> None:
        validate_scenario(scenario, tier=tier, inventory=inventory, ownership=ownership)
        self.scenario = scenario
        self.operations = {row["operationId"]: row for row in inventory["operations"]}
        self.tier = tier
        self.adapter = adapter
        self.environ = environ
        self.run_id = run_id or uuid.uuid4().hex
        self.run_prefix = f"postgrip-sdk-{tier.replace('-', '')}-{self.run_id[:12]}"
        if not NAME_PATTERN.fullmatch(self.run_prefix):
            raise LiveSuiteError("generated run prefix is not a safe resource name")
        self.destructive_enabled = (
            scenario["disposableEnvironment"]
            and environ.get("POSTGRIP_LIVE_DISPOSABLE") == "true"
            and allow_destructive
        )
        self.variables: dict[str, Any] = {}
        self.ledger = CleanupLedger(
            ledger_path,
            tier=tier,
            run_id=self.run_id,
            run_prefix=self.run_prefix,
            digest=inventory["contractBundleDigest"],
        )
        for resource in scenario["seedResources"]:
            self._register_resource(resource)

    def _redact(self, value: object) -> str:
        text = str(value)
        for name, secret in self.environ.items():
            if (
                any(marker in name for marker in ("TOKEN", "CREDENTIAL", "PRIVATE_KEY"))
                and secret
            ):
                text = text.replace(secret, "[REDACTED]")
        for name, secret in self.variables.items():
            if (
                any(
                    marker in name.upper()
                    for marker in (
                        "TOKEN",
                        "TICKET",
                        "SECRET",
                        "CREDENTIAL",
                        "PRIVATE_KEY",
                    )
                )
                and isinstance(secret, str)
                and secret
            ):
                text = text.replace(secret, "[REDACTED]")
        return text

    def _resolve(self, value: Any) -> Any:
        return resolve_template(
            value, self.variables, self.environ, self.run_id, self.run_prefix
        )

    def _register_resource(self, descriptor: Mapping[str, Any]) -> None:
        resolved = self._resolve(
            {name: descriptor[name] for name in ("key", "kind", "identifier", "name")}
        )
        cleanup = dict(descriptor["cleanup"])
        name = str(resolved["name"])
        key = str(resolved["key"])
        if any(item.key == key for item in self.ledger.resources):
            raise LiveSuiteError(f"duplicate resolved resource key {key!r}")
        if self.run_prefix not in name:
            raise LiveSuiteError(
                f"resource {resolved['key']!r} name does not contain this run's unique prefix"
            )
        identifier = str(resolved["identifier"])
        if not identifier or "*" in identifier:
            raise LiveSuiteError(
                f"resource {resolved['key']!r} has an unsafe identifier"
            )
        cleanup_operation = self.operations[cleanup["operationId"]]
        if cleanup_operation["safety"] not in {"mutation", "destructive"}:
            raise LiveSuiteError(
                f"resource {resolved['key']!r} cleanup is not a mutating operation"
            )
        cleanup_paths = {
            str(item)
            for item in self._resolve(cleanup["request"]["pathParameters"]).values()
        }
        if identifier not in cleanup_paths:
            raise LiveSuiteError(
                f"resource {resolved['key']!r} cleanup does not use its explicit identifier "
                "as a path parameter"
            )
        self.ledger.resources.append(
            ResourceRecord(
                key=key,
                kind=str(resolved["kind"]),
                identifier=identifier,
                name=name,
                cleanup=cleanup,
            )
        )
        self.ledger.write()

    def _resource(self, key: str) -> ResourceRecord:
        matches = [item for item in self.ledger.resources if item.key == key]
        if len(matches) != 1:
            raise LiveSuiteError(f"operation references unregistered resource {key!r}")
        return matches[0]

    def _require_safe_target(
        self, operation: Mapping[str, Any], step: Mapping[str, Any]
    ) -> None:
        safety = operation["safety"]
        if safety in {"mutation", "destructive", "protocol"}:
            resource_key = step["resourceKey"]
            if resource_key is None and step["createsResource"] is None:
                raise LiveSuiteError(
                    f"{operation['operationId']} must target or create an explicitly recorded resource"
                )
            if resource_key is not None:
                resource = self._resource(resource_key)
                if resource.cleaned:
                    raise LiveSuiteError(
                        f"{operation['operationId']} targets already-cleaned resource {resource_key!r}"
                    )
        if safety == "destructive" and not self.destructive_enabled:
            raise LiveSuiteError(
                f"refusing destructive operation {operation['operationId']}: require scenario "
                "disposableEnvironment=true, POSTGRIP_LIVE_DISPOSABLE=true, and --allow-destructive"
            )

    def _validate_explicit_paths(
        self, request: Mapping[str, Any], operation_id: str
    ) -> None:
        for name, value in request["pathParameters"].items():
            text = str(value)
            if not text or "*" in text:
                raise LiveSuiteError(
                    f"{operation_id} has unsafe path parameter {name!r}"
                )

    def execute_step(self, step: Mapping[str, Any]) -> None:
        operation = self.operations[step["operationId"]]
        self._require_safe_target(operation, step)
        request = self._resolve(step["request"])
        self._validate_explicit_paths(request, operation["operationId"])
        resource_key = step["resourceKey"]
        if (
            operation["safety"] in {"mutation", "destructive", "protocol"}
            and resource_key is not None
        ):
            resource = self._resource(resource_key)
            if not contains_scalar(request, resource.identifier):
                raise LiveSuiteError(
                    f"{operation['operationId']} request does not contain the recorded "
                    f"identifier {resource.identifier!r} for resource {resource_key!r}"
                )
        if step["createsResource"] is not None:
            resource_name = str(self._resolve(step["createsResource"]["name"]))
            if not contains_scalar(request, resource_name):
                raise LiveSuiteError(
                    f"{operation['operationId']} request does not contain its run-prefixed "
                    "resource name"
                )
        for key in step["cleansResources"]:
            expected = self._resolve(self._resource(key).cleanup)
            if (
                operation["operationId"] != expected["operationId"]
                or request != expected["request"]
            ):
                raise LiveSuiteError(
                    f"{operation['operationId']} does not match the recorded cleanup for "
                    f"resource {key!r}"
                )
        try:
            response = self.adapter.execute(operation, request)
        except Exception as exc:
            raise LiveSuiteError(
                f"{operation['plane']}/{operation['operationId']} failed: "
                f"{type(exc).__name__}: {self._redact(exc)}"
            ) from exc
        for name, pointer in step["capture"].items():
            self.variables[name] = json_pointer(response, pointer)
        if step["createsResource"] is not None:
            self._register_resource(step["createsResource"])
        for key in step["cleansResources"]:
            self._resource(key).cleaned = True
        self.ledger.operations.append(
            OperationRecord(
                operation["operationId"], operation["plane"], "passed", utc_now()
            )
        )
        self.ledger.write()

    def cleanup(self) -> list[str]:
        failures: list[str] = []
        for resource in reversed(self.ledger.resources):
            if resource.cleaned:
                continue
            cleanup = self._resolve(resource.cleanup)
            operation = self.operations[cleanup["operationId"]]
            if operation["safety"] == "destructive" and not self.destructive_enabled:
                message = "destructive cleanup guard is not enabled"
                resource.cleanup_error = message
                failures.append(f"{resource.kind}/{resource.identifier}: {message}")
                self.ledger.write()
                continue
            try:
                self._validate_explicit_paths(
                    cleanup["request"], operation["operationId"]
                )
                self.adapter.execute(operation, cleanup["request"])
                resource.cleaned = True
            except Exception as exc:  # noqa: BLE001 - cleanup must continue after one resource fails
                resource.cleanup_error = f"{type(exc).__name__}: {self._redact(exc)}"
                failures.append(
                    f"{resource.kind}/{resource.identifier}: {resource.cleanup_error}"
                )
            self.ledger.write()
        return failures

    def run(self) -> None:
        primary: str | None = None
        cleanup_failures: list[str] = []
        try:
            for step in self.scenario["steps"]:
                self.execute_step(step)
        except Exception as exc:  # noqa: BLE001 - cleanup must run for every primary failure
            primary = self._redact(exc)
            self.ledger.primary_failure = primary
        finally:
            cleanup_failures = self.cleanup()
            self.ledger.finished_at = utc_now()
            self.ledger.status = "failed" if primary or cleanup_failures else "passed"
            self.ledger.write()
        if primary or cleanup_failures:
            details = []
            if primary:
                details.append(f"primary failure: {primary}")
            if cleanup_failures:
                details.append("cleanup failures: " + "; ".join(cleanup_failures))
            remaining = [
                item.identifier for item in self.ledger.resources if not item.cleaned
            ]
            if remaining:
                details.append("remaining identifiers: " + ", ".join(remaining))
            raise LiveSuiteError(" | ".join(details))


class PythonSDKAdapter:
    """Execute live operations through the installed unified Python SDK."""

    def __init__(
        self, environ: Mapping[str, str], *, insecure_development: bool
    ) -> None:
        from postgrip.agent import Client as AgentClient
        from postgrip.agent import Connection
        from postgrip.service import ServiceClient
        from postgrip.worker import WorkerClient

        token = environ.get("POSTGRIP_TOKEN", "")
        common = environ.get("POSTGRIP_URL", "")
        agent_url = environ.get("POSTGRIP_AGENT_URL") or common
        worker_url = environ.get("POSTGRIP_WORKER_URL") or common
        service_url = environ.get("POSTGRIP_SERVICE_URL") or common
        if not token or not agent_url or not worker_url or not service_url:
            raise LiveSuiteError(
                "POSTGRIP_TOKEN and POSTGRIP_URL (or all three plane URLs) are required"
            )
        self.token = token
        self.connection = Connection(
            agent_url,
            auth_token=token,
            insecure_development=insecure_development,
            timeout=30,
        )
        self.agent = AgentClient(self.connection)
        self.workers = WorkerClient(
            base_url=worker_url,
            token=token,
            insecure_development=insecure_development,
            timeout=30,
        )
        self.services = ServiceClient(
            base_url=service_url,
            token=token,
            insecure_development=insecure_development,
            timeout=30,
        )

    def execute(self, operation: Mapping[str, Any], request: Mapping[str, Any]) -> Any:
        plane = operation["plane"]
        operation_id = operation["operationId"]
        if operation_id == "uploadWorkspace":
            archive = base64.b64decode(request["streamBodyBase64"], validate=True)
            return self.agent.sandbox.upload_workspace(
                archive,
                repository_name=request["headers"].get("X-PostGrip-Repository"),
                revision=request["headers"].get("X-PostGrip-Revision"),
            )
        if operation_id == "connectSandboxSession":
            from postgrip.agent.sandbox import SandboxSession, sandbox_relay_url

            url = sandbox_relay_url(
                self.connection.address,
                str(request["pathParameters"]["sessionId"]),
                str(request["query"]["ticket"]),
                insecure_development=self.connection.insecure_development,
            )
            with SandboxSession(url, {"Authorization": f"Bearer {self.token}"}):
                return None
        if operation_id == "listServiceLogs" and request["query"].get("follow") is True:
            from postgrip.service.client import ServiceReference

            path = request["pathParameters"]
            query = request["query"]
            cancel = Event()
            timer = Timer(2.0, cancel.set)
            timer.start()
            try:
                entries = self.services.follow_logs(
                    ServiceReference(path["source"], path["serviceId"]),
                    cancel=cancel,
                    kind=query.get("kind"),
                    environment_id=query.get("environment"),
                    deployment_id=query.get("deployment"),
                    limit=query.get("limit"),
                    cursor=query.get("cursor"),
                )
                try:
                    return {"items": [next(entries)]}
                except StopIteration:
                    return {"items": []}
                finally:
                    entries.close()
            finally:
                cancel.set()
                timer.cancel()
        if plane == "agent":
            from postgrip.agent.openapi import OperationId

            client = self.connection.openapi
            operation_key: Any = OperationId(operation_id)
        elif plane == "worker":
            from postgrip.worker.openapi import OperationId

            client = self.workers.openapi
            operation_key = OperationId(operation_id)
        else:
            from postgrip.service.openapi import OperationId

            client = self.services.openapi
            operation_key = OperationId(operation_id)
        return client.request(
            operation_key,
            request["body"],
            path_parameters=request["pathParameters"],
            query=request["query"],
            headers=request["headers"],
        )


class FakeAdapter:
    def __init__(
        self, responses: Mapping[str, Any], failures: set[str] | None = None
    ) -> None:
        self.responses = responses
        self.failures = failures or set()
        self.calls: list[str] = []

    def execute(self, operation: Mapping[str, Any], request: Mapping[str, Any]) -> Any:
        operation_id = operation["operationId"]
        self.calls.append(operation_id)
        if operation_id in self.failures:
            raise RuntimeError("injected failure")
        return self.responses.get(operation_id)


def self_test() -> None:
    operations = [
        {
            "operationId": "createA",
            "plane": "agent",
            "safety": "mutation",
            "authLane": "management",
        },
        {
            "operationId": "createB",
            "plane": "agent",
            "safety": "mutation",
            "authLane": "management",
        },
        {
            "operationId": "inspect",
            "plane": "agent",
            "safety": "mutation",
            "authLane": "management",
        },
        {
            "operationId": "deleteA",
            "plane": "agent",
            "safety": "destructive",
            "authLane": "management",
        },
        {
            "operationId": "deleteB",
            "plane": "agent",
            "safety": "destructive",
            "authLane": "management",
        },
    ]
    inventory = {"contractBundleDigest": "self-test", "operations": operations}
    ownership = {
        name: {"liveTest": "nightly"} for name in ("createA", "createB", "inspect")
    }
    empty_request = {
        "pathParameters": {},
        "query": {},
        "headers": {},
        "body": None,
        "streamBodyBase64": None,
    }

    def create_request(key: str) -> dict[str, Any]:
        request = dict(empty_request)
        request["body"] = {"name": f"${{runPrefix}}-{key.lower()}"}
        return request

    def resource(key: str, capture: str, cleanup_operation: str) -> dict[str, Any]:
        request = dict(empty_request)
        request["pathParameters"] = {"id": f"${{var.{capture}}}"}
        return {
            "key": key,
            "kind": "fixture",
            "identifier": f"${{var.{capture}}}",
            "name": f"${{runPrefix}}-{key.lower()}",
            "cleanup": {"operationId": cleanup_operation, "request": request},
        }

    scenario = {
        "schemaVersion": 1,
        "contractBundleDigest": "self-test",
        "tier": "nightly",
        "disposableEnvironment": True,
        "seedResources": [],
        "steps": [
            {
                "operationId": "createA",
                "request": create_request("a"),
                "capture": {"a": "/id"},
                "resourceKey": None,
                "createsResource": resource("a", "a", "deleteA"),
                "cleansResources": [],
            },
            {
                "operationId": "createB",
                "request": create_request("b"),
                "capture": {"b": "/id"},
                "resourceKey": None,
                "createsResource": resource("b", "b", "deleteB"),
                "cleansResources": [],
            },
            {
                "operationId": "inspect",
                "request": {
                    **empty_request,
                    "pathParameters": {"id": "${var.b}"},
                },
                "capture": {},
                "resourceKey": "b",
                "createsResource": None,
                "cleansResources": [],
            },
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        adapter = FakeAdapter({"createA": {"id": "id-a"}, "createB": {"id": "id-b"}})
        manager = FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=adapter,
            environ={"POSTGRIP_LIVE_DISPOSABLE": "true"},
            ledger_path=Path(directory) / "ledger.json",
            allow_destructive=True,
            run_id="0123456789abcdef",
        )
        manager.run()
        if adapter.calls != ["createA", "createB", "inspect", "deleteB", "deleteA"]:
            raise AssertionError(
                f"cleanup was not reverse dependency order: {adapter.calls}"
            )
        ledger = load_json(Path(directory) / "ledger.json")
        if ledger["status"] != "passed" or ledger["remainingIdentifiers"]:
            raise AssertionError("successful cleanup ledger is incomplete")

        mismatched_scenario = json.loads(json.dumps(scenario))
        mismatched_scenario["steps"][2]["request"]["pathParameters"]["id"] = "${var.a}"
        mismatched = FixtureManager(
            scenario=mismatched_scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=FakeAdapter(
                {"createA": {"id": "id-a"}, "createB": {"id": "id-b"}}
            ),
            environ={"POSTGRIP_LIVE_DISPOSABLE": "true"},
            ledger_path=Path(directory) / "mismatched.json",
            allow_destructive=True,
            run_id="0011223344556677",
        )
        try:
            mismatched.run()
        except LiveSuiteError as exc:
            if "does not contain the recorded identifier 'id-b'" not in str(exc):
                raise AssertionError(
                    "target mismatch did not identify the recorded resource"
                ) from exc
        else:
            raise AssertionError("targeted mutation accepted another resource identifier")

        guarded = FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=FakeAdapter({"createA": {"id": "id-a"}, "createB": {"id": "id-b"}}),
            environ={"POSTGRIP_LIVE_DISPOSABLE": "false"},
            ledger_path=Path(directory) / "guarded.json",
            allow_destructive=True,
            run_id="fedcba9876543210",
        )
        try:
            guarded.run()
        except LiveSuiteError as exc:
            if "destructive cleanup guard" not in str(exc) or "id-b" not in str(exc):
                raise AssertionError(
                    "guard failure did not preserve remaining identifiers"
                ) from exc
        else:
            raise AssertionError("cleanup ran without the disposable marker")

        failing = FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=FakeAdapter(
                {"createA": {"id": "id-a"}, "createB": {"id": "id-b"}},
                failures={"inspect", "deleteB"},
            ),
            environ={"POSTGRIP_LIVE_DISPOSABLE": "true"},
            ledger_path=Path(directory) / "failure.json",
            allow_destructive=True,
            run_id="abcdef0123456789",
        )
        try:
            failing.run()
        except LiveSuiteError as exc:
            message = str(exc)
            if (
                "primary failure" not in message
                or "cleanup failures" not in message
                or "id-b" not in message
            ):
                raise AssertionError(
                    "primary and cleanup failures were not both reported"
                ) from exc
        else:
            raise AssertionError("injected live failure unexpectedly passed")
    print("Live fixture-manager self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=TIERS)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument(
        "--ledger", type=Path, default=Path("test/reports/live-ledger.json")
    )
    parser.add_argument("--allow-destructive", action="store_true")
    parser.add_argument("--insecure-development", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.tier is None:
        parser.error("--tier is required unless --self-test is used")
    try:
        inventory = load_json(INVENTORY_PATH)
        ownership = load_json(OWNERSHIP_PATH)["operations"]
        scenario = load_scenario(args.scenario, os.environ)
        validate_scenario(
            scenario, tier=args.tier, inventory=inventory, ownership=ownership
        )
        if args.validate_only:
            print(
                f"Live scenario validated: tier={args.tier}, operations={len(scenario['steps'])}, "
                f"bundle={inventory['contractBundleDigest'][:12]}"
            )
            return 0
        adapter = PythonSDKAdapter(
            os.environ, insecure_development=args.insecure_development
        )
        manager = FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier=args.tier,
            adapter=adapter,
            environ=os.environ,
            ledger_path=args.ledger,
            allow_destructive=args.allow_destructive,
        )
        manager.run()
    except (LiveSuiteError, KeyError, TypeError, ValueError) as exc:
        print(f"Live API suite failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Live API suite passed: tier={args.tier}, operations={len(scenario['steps'])}, "
        f"ledger={args.ledger}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
