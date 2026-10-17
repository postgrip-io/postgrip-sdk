#!/usr/bin/env python3
"""Run contract-owned live API scenarios with disposable-resource safeguards.

The checked-in operation ownership file decides cadence. Environment-specific
scenario data supplies valid repository, worker, image, and host-runtime
fixtures without committing credentials or durable identifiers to this repo.
"""

from __future__ import annotations

import argparse
import base64
import functools
import gzip
import json
import os
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
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
STEP_FIELDS = frozenset(
    {
        "operationId",
        "request",
        "capture",
        "resourceKey",
        "createsResource",
        "cleansResources",
    }
)
# Optional step modes. A step with none of them is a counted coverage step.
STEP_MODES = frozenset({"fixture", "rotatesCredentials", "wait"})
# A resource's lifecycle decides how this run disposes of it. Only "cleanup"
# resources can remain; the others are reported as consumed, expired, or left
# for the stage reset.
LIFECYCLES = ("cleanup", "transient", "reset-owned")
# Set by the live workflows to the stage-lease run ID once that job's lease
# `start` step succeeded. Reset-owned resources are accepted only under it.
STAGE_LEASE_ENV = "POSTGRIP_LIVE_STAGE_LEASE"
STAGE_LEASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
REFRESH_CREDENTIAL = "agent-refresh-token"
WAIT_MAX_INTERVAL_SECONDS = 60
WAIT_MAX_TIMEOUT_SECONDS = 1800
# Credential headers are never filled from a response.
UNFILLABLE_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie"})


class LiveSuiteError(RuntimeError):
    """A safe, redacted live-suite failure."""


class OperationAdapter(Protocol):
    def execute(
        self, operation: Mapping[str, Any], request: Mapping[str, Any]
    ) -> Any: ...

    def rotate_agent_session(self, operation: Mapping[str, Any]) -> None:
        """Send the connection's current refresh token through ``operation``
        and apply the returned tokens to that connection. Tokens never leave
        the adapter."""
        ...

    def sensitive_values(self) -> Iterable[str]:
        """Credentials the adapter holds that are not in the environment."""
        ...


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


def set_json_pointer(document: Any, pointer: str, value: Any) -> None:
    """Set an object member named by a non-empty JSON pointer."""

    if not pointer.startswith("/"):
        raise LiveSuiteError(f"fill pointer {pointer!r} must start with '/'")
    parent_pointer, _, raw = pointer.rpartition("/")
    parent = json_pointer(document, parent_pointer)
    if not isinstance(parent, dict):
        raise LiveSuiteError(f"fill pointer {pointer!r} does not name an object member")
    parent[raw.replace("~1", "/").replace("~0", "~")] = value


def remove_json_pointer(document: Any, pointer: str) -> None:
    parent_pointer, _, raw = pointer.rpartition("/")
    try:
        parent = json_pointer(document, parent_pointer)
    except LiveSuiteError:
        return
    if isinstance(parent, dict):
        parent.pop(raw.replace("~1", "/").replace("~0", "~"), None)


def json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int and int/float coercion."""

    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def step_role(step: Mapping[str, Any]) -> str:
    """Return how a step counts: wait and fixture steps never cover operations."""

    if "wait" in step:
        return "wait"
    if step.get("fixture") is True:
        return "fixture"
    return "counted"


def resource_lifecycle(descriptor: Mapping[str, Any]) -> str:
    return str(descriptor.get("lifecycle", "cleanup"))


def is_credential_operation(operation: Mapping[str, Any]) -> bool:
    return REFRESH_CREDENTIAL in operation.get("acceptedCredentials", ())


def read_stage_lease(environ: Mapping[str, str]) -> str | None:
    value = environ.get(STAGE_LEASE_ENV, "").strip()
    if not value:
        return None
    if not STAGE_LEASE_PATTERN.fullmatch(value):
        raise LiveSuiteError(f"{STAGE_LEASE_ENV} is not a stage-lease run ID")
    return value


def contains_scalar(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return any(contains_scalar(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(contains_scalar(item, expected) for item in value)
    return str(value) == expected


def referenced_variables(value: Any) -> set[str]:
    """Return captured variable names referenced by a scenario value."""

    if isinstance(value, dict):
        return set().union(*(referenced_variables(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(referenced_variables(item) for item in value))
    if not isinstance(value, str):
        return set()
    return {
        match.group(1).removeprefix("var.")
        for match in PLACEHOLDER.finditer(value)
        if match.group(1).startswith("var.")
    }


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


def validate_pointer_map(value: Any, location: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and name and isinstance(pointer, str)
        for name, pointer in value.items()
    ):
        raise LiveSuiteError(f"{location} must map names to JSON pointers")
    for pointer in value.values():
        if pointer and not pointer.startswith("/"):
            raise LiveSuiteError(f"{location} pointer {pointer!r} must start with '/'")
    return value


def validate_cleanup_refresh(
    value: Any,
    location: str,
    operations: Mapping[str, Any],
    cleanup_request: Mapping[str, Any],
) -> dict[str, Any]:
    """A read run just before a cleanup to fill its precondition fields.

    Only headers and body members can be filled. Path parameters (the target)
    and the query stay frozen at registration.
    """

    required = {"operationId", "request", "headers", "body"}
    if not isinstance(value, dict) or set(value) != required:
        raise LiveSuiteError(f"{location} must contain exactly {sorted(required)}")
    operation_id = value["operationId"]
    if operation_id not in operations:
        raise LiveSuiteError(
            f"{location} references unknown operation {operation_id!r}"
        )
    if operations[operation_id]["safety"] != "read-only":
        raise LiveSuiteError(f"{location} operation {operation_id} is not read-only")
    validate_request(value["request"], f"{location}.request")
    headers = validate_pointer_map(value["headers"], f"{location}.headers")
    body = validate_pointer_map(value["body"], f"{location}.body")
    if not headers and not body:
        raise LiveSuiteError(f"{location} must fill at least one precondition field")
    for name in headers:
        if name.lower() in UNFILLABLE_HEADERS:
            raise LiveSuiteError(f"{location} cannot fill credential header {name!r}")
    for target in body:
        if not target.startswith("/"):
            raise LiveSuiteError(
                f"{location}.body field {target!r} must be a JSON pointer"
            )
    if body and not isinstance(cleanup_request["body"], dict):
        raise LiveSuiteError(
            f"{location}.body fills require the cleanup request body to be an object"
        )
    return value


def validate_cleanup(
    value: Any, location: str, operations: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, dict) or not (
        {"operationId", "request"}
        <= set(value)
        <= {"operationId", "request", "refresh"}
    ):
        raise LiveSuiteError(
            f"{location} must contain operationId and request, and optionally refresh"
        )
    operation_id = value["operationId"]
    if operation_id not in operations:
        raise LiveSuiteError(
            f"{location} references unknown operation {operation_id!r}"
        )
    validate_request(value["request"], f"{location}.request")
    if "refresh" in value:
        validate_cleanup_refresh(
            value["refresh"], f"{location}.refresh", operations, value["request"]
        )
    return value


def validate_resource(
    value: Any, location: str, operations: Mapping[str, Any], *, seeded: bool
) -> dict[str, Any]:
    required = {"key", "kind", "identifier", "name", "cleanup"}
    if not isinstance(value, dict) or not (
        required <= set(value) <= required | {"lifecycle"}
    ):
        raise LiveSuiteError(
            f"{location} must contain exactly {sorted(required)} and optionally lifecycle"
        )
    for name in ("key", "kind", "identifier", "name"):
        if not isinstance(value[name], str) or not value[name]:
            raise LiveSuiteError(f"{location}.{name} must be a non-empty string")
    lifecycle = resource_lifecycle(value)
    if lifecycle not in LIFECYCLES:
        raise LiveSuiteError(f"{location}.lifecycle must be one of {list(LIFECYCLES)}")
    if lifecycle == "cleanup":
        validate_cleanup(value["cleanup"], f"{location}.cleanup", operations)
    elif value["cleanup"] is not None:
        raise LiveSuiteError(f"{location} is {lifecycle} and must have a null cleanup")
    if seeded and lifecycle != "cleanup":
        raise LiveSuiteError(f"{location} seeded resources must use cleanup lifecycle")
    if seeded and "${runPrefix}" not in value["name"]:
        raise LiveSuiteError(f"{location}.name must contain ${{runPrefix}}")
    return value


def validate_wait(
    value: Any, location: str, capture: Mapping[str, str], captured_names: set[str]
) -> dict[str, Any]:
    required = {"capture", "equals", "intervalSeconds", "timeoutSeconds"}
    if not isinstance(value, dict) or set(value) != required:
        raise LiveSuiteError(f"{location} must contain exactly {sorted(required)}")
    if value["capture"] not in capture:
        raise LiveSuiteError(f"{location}.capture must name one of the step's captures")
    bounds = {
        "intervalSeconds": WAIT_MAX_INTERVAL_SECONDS,
        "timeoutSeconds": WAIT_MAX_TIMEOUT_SECONDS,
    }
    for name, maximum in bounds.items():
        seconds = value[name]
        if (
            not isinstance(seconds, int)
            or isinstance(seconds, bool)
            or not 1 <= seconds <= maximum
        ):
            raise LiveSuiteError(
                f"{location}.{name} must be an integer from 1 to {maximum}"
            )
    if value["intervalSeconds"] > value["timeoutSeconds"]:
        raise LiveSuiteError(f"{location}.intervalSeconds exceeds timeoutSeconds")
    unavailable = referenced_variables(value["equals"]) - captured_names
    if unavailable:
        raise LiveSuiteError(
            f"{location}.equals references unavailable captures {sorted(unavailable)}"
        )
    return value


def validate_step_mode(
    step: Mapping[str, Any],
    location: str,
    operation: Mapping[str, Any],
    captured_names: set[str],
) -> None:
    """Check the fixture, wait, and credential markers a step may carry."""

    for flag in ("fixture", "rotatesCredentials"):
        if flag in step and not isinstance(step[flag], bool):
            raise LiveSuiteError(f"{location}.{flag} must be boolean")
    rotates = step.get("rotatesCredentials", False)
    operation_id = operation["operationId"]
    if is_credential_operation(operation) and not rotates:
        raise LiveSuiteError(
            f"{location} {operation_id} accepts an Agent refresh token and must be a "
            "credential step (rotatesCredentials: true)"
        )
    if rotates:
        if not is_credential_operation(operation):
            raise LiveSuiteError(
                f"{location} credential steps must name an operation that accepts an "
                "Agent refresh token"
            )
        if operation["plane"] != "agent":
            raise LiveSuiteError(
                f"{location} credential steps rotate the Agent session"
            )
        request = step["request"]
        # The manager supplies the refresh token. A scenario must not send or
        # capture session credentials.
        if (
            request["pathParameters"]
            or request["query"]
            or request["headers"]
            or request["body"] is not None
            or request["streamBodyBase64"] is not None
        ):
            raise LiveSuiteError(f"{location} credential step request must be empty")
        if step["capture"]:
            raise LiveSuiteError(
                f"{location} credential step cannot capture its response"
            )
    if "wait" in step:
        validate_wait(step["wait"], f"{location}.wait", step["capture"], captured_names)
        if operation["safety"] != "read-only":
            raise LiveSuiteError(
                f"{location} wait operation {operation_id} is not read-only"
            )
    if rotates and step["resourceKey"] is not None:
        raise LiveSuiteError(f"{location} credential steps cannot target a resource")
    if (rotates or "wait" in step) and (
        step["createsResource"] is not None or step["cleansResources"]
    ):
        raise LiveSuiteError(
            f"{location} wait and credential steps cannot create or clean resources"
        )


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
    captured_names: set[str] = set()
    for index, resource in enumerate(seeds):
        validated = validate_resource(
            resource, f"seedResources[{index}]", operations, seeded=True
        )
        if validated["key"] in keys:
            raise LiveSuiteError(f"duplicate resource key {validated['key']!r}")
        if referenced_variables(validated):
            raise LiveSuiteError(
                f"seedResources[{index}] cannot reference response captures"
            )
        keys.add(validated["key"])
    lifecycles = {resource["key"]: "cleanup" for resource in seeds}
    consumed_transients: set[str] = set()
    actual_ids: list[str] = []
    for index, step in enumerate(steps):
        location = f"steps[{index}]"
        if not isinstance(step, dict) or not (
            STEP_FIELDS <= set(step) <= STEP_FIELDS | STEP_MODES
        ):
            raise LiveSuiteError(
                f"{location} must contain exactly {sorted(STEP_FIELDS)} and "
                f"optionally {sorted(STEP_MODES)}"
            )
        if tier == "production-smoke" and set(step) != STEP_FIELDS:
            raise LiveSuiteError(
                f"{location} production smoke steps cannot be fixture, wait, or "
                "credential steps"
            )
        operation_id = step["operationId"]
        if operation_id not in operations:
            raise LiveSuiteError(
                f"{location} references unknown operation {operation_id!r}"
            )
        # Fixture and wait steps set up prerequisites; only counted steps
        # cover the tier's operations.
        if step_role(step) == "counted":
            actual_ids.append(operation_id)
        validate_request(step["request"], f"{location}.request")
        capture = step["capture"]
        if not isinstance(capture, dict) or not all(
            isinstance(name, str) and name and isinstance(pointer, str)
            for name, pointer in capture.items()
        ):
            raise LiveSuiteError(f"{location}.capture must map names to JSON pointers")
        duplicate_captures = captured_names.intersection(capture)
        if duplicate_captures:
            raise LiveSuiteError(
                f"{location}.capture redefines variables {sorted(duplicate_captures)}"
            )
        unavailable_request_captures = referenced_variables(step["request"]) - captured_names
        if unavailable_request_captures:
            raise LiveSuiteError(
                f"{location}.request references unavailable captures "
                f"{sorted(unavailable_request_captures)}"
            )
        resource_key = step["resourceKey"]
        if resource_key is not None and (
            not isinstance(resource_key, str) or not resource_key
        ):
            raise LiveSuiteError(f"{location}.resourceKey must be a string or null")
        validate_step_mode(step, location, operations[operation_id], captured_names)
        if resource_key is not None and lifecycles.get(resource_key) == "transient":
            if operations[operation_id]["safety"] != "protocol":
                raise LiveSuiteError(
                    f"{location} targets transient resource {resource_key!r}; only a "
                    "protocol step may consume it"
                )
            if resource_key in consumed_transients:
                raise LiveSuiteError(
                    f"{location} transient resource {resource_key!r} is already consumed"
                )
            consumed_transients.add(resource_key)
        creates = step["createsResource"]
        if creates is not None:
            validated = validate_resource(
                creates, f"{location}.createsResource", operations, seeded=False
            )
            if validated["key"] in keys:
                raise LiveSuiteError(f"duplicate resource key {validated['key']!r}")
            unavailable_intent_captures = referenced_variables(
                {name: validated[name] for name in ("key", "kind", "name")}
            ) - captured_names
            if unavailable_intent_captures:
                raise LiveSuiteError(
                    f"{location}.createsResource intent references unavailable captures "
                    f"{sorted(unavailable_intent_captures)}"
                )
            unavailable_resource_captures = referenced_variables(validated) - (
                captured_names | set(capture)
            )
            if unavailable_resource_captures:
                raise LiveSuiteError(
                    f"{location}.createsResource references unavailable captures "
                    f"{sorted(unavailable_resource_captures)}"
                )
            if (
                tier == "production-smoke"
                and resource_lifecycle(validated) != "cleanup"
            ):
                raise LiveSuiteError(
                    f"{location} production smoke cannot leave resources uncleaned"
                )
            keys.add(validated["key"])
            lifecycles[validated["key"]] = resource_lifecycle(validated)
        cleaned = step["cleansResources"]
        if not isinstance(cleaned, list) or not all(
            isinstance(key, str) and key for key in cleaned
        ):
            raise LiveSuiteError(
                f"{location}.cleansResources must be an array of resource keys"
            )
        for key in cleaned:
            if lifecycles.get(key, "cleanup") != "cleanup":
                raise LiveSuiteError(
                    f"{location} cannot clean {lifecycles[key]} resource {key!r}"
                )
        captured_names.update(capture)

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
    identifier: str | None
    name: str
    cleanup: dict[str, Any] | None = field(repr=False)
    cleaned: bool = False
    cleanup_error: str | None = None
    lifecycle: str = "cleanup"
    consumed: bool = False

    @property
    def remaining(self) -> bool:
        """Only a cleanup-owned resource can be left behind by this run."""

        return self.lifecycle == "cleanup" and not self.cleaned

    @property
    def outcome(self) -> str:
        if self.lifecycle == "transient":
            return "consumed" if self.consumed else "expired"
        if self.lifecycle == "reset-owned":
            return "left-for-stage-reset"
        return "cleaned" if self.cleaned else "remaining"


@dataclass
class OperationRecord:
    operation_id: str
    plane: str
    status: str
    completed_at: str
    role: str = "counted"


class CleanupLedger:

    def __init__(
        self,
        path: Path,
        *,
        tier: str,
        run_id: str,
        run_prefix: str,
        digest: str,
        stage_lease: str | None = None,
    ) -> None:
        self.path = path
        self.tier = tier
        self.run_id = run_id
        self.run_prefix = run_prefix
        self.digest = digest
        self.stage_lease = stage_lease
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
            "stageLease": self.stage_lease,
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
                    "lifecycle": item.lifecycle,
                    "outcome": item.outcome,
                    "cleaned": item.cleaned,
                    "cleanupError": item.cleanup_error,
                }
                for item in self.resources
            ],
            "remainingIdentifiers": self._identifiers("remaining"),
            "consumedIdentifiers": self._identifiers("consumed"),
            "expiredIdentifiers": self._identifiers("expired"),
            "stageResetIdentifiers": self._identifiers("left-for-stage-reset"),
        }

    def _identifiers(self, outcome: str) -> list[str]:
        return [
            item.identifier or item.name
            for item in self.resources
            if item.outcome == outcome
        ]

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


def precondition_value(response: Any, pointer: str) -> Any:
    value = json_pointer(response, pointer)
    if isinstance(value, (dict, list)) or value is None:
        raise LiveSuiteError(f"cleanup refresh pointer {pointer!r} is not a scalar")
    return value


def without_preconditions(
    request: Mapping[str, Any], refresh: Mapping[str, Any] | None
) -> dict[str, Any]:
    """A cleanup request minus the fields its refresh may fill, for comparison."""

    stripped = json.loads(json.dumps(request))
    if refresh is None:
        return stripped
    filled = {name.lower() for name in refresh["headers"]}
    stripped["headers"] = {
        name: value
        for name, value in stripped["headers"].items()
        if name.lower() not in filled
    }
    for target in refresh["body"]:
        remove_json_pointer(stripped["body"], target)
    return stripped


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
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        validate_scenario(scenario, tier=tier, inventory=inventory, ownership=ownership)
        self.scenario = scenario
        self.operations = {row["operationId"]: row for row in inventory["operations"]}
        self.tier = tier
        self.adapter = adapter
        self.environ = environ
        self.clock = clock
        self.sleep = sleep
        self.run_id = run_id or uuid.uuid4().hex
        self.run_prefix = f"postgrip-sdk-{tier.replace('-', '')}-{self.run_id[:12]}"
        if not NAME_PATTERN.fullmatch(self.run_prefix):
            raise LiveSuiteError("generated run prefix is not a safe resource name")
        self.destructive_enabled = (
            scenario["disposableEnvironment"]
            and environ.get("POSTGRIP_LIVE_DISPOSABLE") == "true"
            and allow_destructive
        )
        # Reset-owned resources are removed only by the stage reset that
        # follows the lease's release, so they are accepted only under one.
        self.stage_lease = read_stage_lease(environ)
        self.stage_reset_enabled = bool(
            self.stage_lease
            and scenario["disposableEnvironment"]
            and environ.get("POSTGRIP_LIVE_DISPOSABLE") == "true"
        )
        declares_reset_owned = any(
            step["createsResource"] is not None
            and resource_lifecycle(step["createsResource"]) == "reset-owned"
            for step in scenario["steps"]
        )
        if declares_reset_owned and not self.stage_reset_enabled:
            raise LiveSuiteError(
                "refusing reset-owned resources: require a held stage lease "
                f"({STAGE_LEASE_ENV}), scenario disposableEnvironment=true, and "
                "POSTGRIP_LIVE_DISPOSABLE=true"
            )
        self.variables: dict[str, Any] = {}
        self.ledger = CleanupLedger(
            ledger_path,
            tier=tier,
            run_id=self.run_id,
            run_prefix=self.run_prefix,
            digest=inventory["contractBundleDigest"],
            stage_lease=self.stage_lease,
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
        # Rotated Agent session tokens live only in the adapter.
        for secret in self.adapter.sensitive_values():
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def _resolve(self, value: Any) -> Any:
        return resolve_template(
            value, self.variables, self.environ, self.run_id, self.run_prefix
        )

    def _call(self, operation: Mapping[str, Any], request: Mapping[str, Any]) -> Any:
        try:
            return self.adapter.execute(operation, request)
        except Exception as exc:
            raise LiveSuiteError(
                f"{operation['plane']}/{operation['operationId']} failed: "
                f"{type(exc).__name__}: {self._redact(exc)}"
            ) from exc

    def _prepare_resource(self, descriptor: Mapping[str, Any]) -> ResourceRecord:
        resolved = self._resolve(
            {name: descriptor[name] for name in ("key", "kind", "name")}
        )
        name = str(resolved["name"])
        key = str(resolved["key"])
        lifecycle = resource_lifecycle(descriptor)
        if any(item.key == key for item in self.ledger.resources):
            raise LiveSuiteError(f"duplicate resolved resource key {key!r}")
        if self.run_prefix not in name:
            raise LiveSuiteError(
                f"resource {resolved['key']!r} name does not contain this run's unique prefix"
            )
        if lifecycle == "reset-owned" and not self.stage_reset_enabled:
            raise LiveSuiteError(
                f"resource {key!r} is reset-owned but this run holds no stage lease"
            )
        if lifecycle == "cleanup":
            cleanup_operation = self.operations[descriptor["cleanup"]["operationId"]]
            if cleanup_operation["safety"] not in {"mutation", "destructive"}:
                raise LiveSuiteError(
                    f"resource {resolved['key']!r} cleanup is not a mutating operation"
                )
        record = ResourceRecord(
            key=key,
            kind=str(resolved["kind"]),
            identifier=None,
            name=name,
            cleanup=None,
            lifecycle=lifecycle,
        )
        self.ledger.resources.append(record)
        # Persist the intent before the network call. A timeout after the
        # server commits is indistinguishable from a pre-commit failure, so a
        # conservative manual-cleanup record is safer than losing ownership.
        self.ledger.write()
        return record

    def _finalize_resource(
        self, record: ResourceRecord, descriptor: Mapping[str, Any]
    ) -> None:
        identifier = str(self._resolve(descriptor["identifier"]))
        if not identifier or "*" in identifier:
            raise LiveSuiteError(f"resource {record.key!r} has an unsafe identifier")
        if record.lifecycle != "cleanup":
            # Transient and reset-owned resources record only their identifier.
            record.identifier = identifier
            self.ledger.write()
            return
        cleanup = self._resolve(descriptor["cleanup"])
        cleanup_paths = {
            str(item) for item in cleanup["request"]["pathParameters"].values()
        }
        if identifier not in cleanup_paths:
            raise LiveSuiteError(
                f"resource {record.key!r} cleanup does not use its explicit identifier "
                "as a path parameter"
            )
        record.identifier = identifier
        # Store the resolved request, not a template backed by mutable capture
        # variables. Cleanup ownership cannot change after registration; a
        # declared refresh may later fill only its header and body fields.
        record.cleanup = cleanup
        self.ledger.write()

    def _register_resource(self, descriptor: Mapping[str, Any]) -> ResourceRecord:
        record = self._prepare_resource(descriptor)
        self._finalize_resource(record, descriptor)
        return record

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
                if resource.identifier is None or (
                    resource.lifecycle == "cleanup" and resource.cleanup is None
                ):
                    raise LiveSuiteError(
                        f"{operation['operationId']} targets unresolved resource {resource_key!r}"
                    )
                if resource.cleaned:
                    raise LiveSuiteError(
                        f"{operation['operationId']} targets already-cleaned resource {resource_key!r}"
                    )
                if resource.lifecycle == "transient" and (
                    safety != "protocol" or resource.consumed
                ):
                    raise LiveSuiteError(
                        f"{operation['operationId']} cannot consume transient resource "
                        f"{resource_key!r}: one protocol step may consume it once"
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
        if step.get("rotatesCredentials"):
            self._rotate_credentials(operation)
        elif "wait" in step:
            self._wait(operation, step)
        else:
            self._execute_operation(operation, step)
        self.ledger.operations.append(
            OperationRecord(
                operation["operationId"],
                operation["plane"],
                "passed",
                utc_now(),
                step_role(step),
            )
        )
        self.ledger.write()

    def _execute_operation(
        self, operation: Mapping[str, Any], step: Mapping[str, Any]
    ) -> None:
        self._require_safe_target(operation, step)
        request = self._resolve(step["request"])
        self._validate_explicit_paths(request, operation["operationId"])
        resource_key = step["resourceKey"]
        target: ResourceRecord | None = None
        if (
            operation["safety"] in {"mutation", "destructive", "protocol"}
            and resource_key is not None
        ):
            target = self._resource(resource_key)
            if not contains_scalar(request["pathParameters"], target.identifier):
                raise LiveSuiteError(
                    f"{operation['operationId']} target path does not contain the recorded "
                    f"identifier {target.identifier!r} for resource {resource_key!r}"
                )
        if step["createsResource"] is not None:
            resource_name = str(self._resolve(step["createsResource"]["name"]))
            # A transient child (a sandbox session) may have no name field; its
            # targeted, run-owned parent carries the run's attribution instead.
            attributed_by_parent = (
                resource_lifecycle(step["createsResource"]) == "transient"
                and target is not None
            )
            if not contains_scalar(request, resource_name) and not attributed_by_parent:
                raise LiveSuiteError(
                    f"{operation['operationId']} request does not contain its run-prefixed "
                    "resource name"
                )
        for key in step["cleansResources"]:
            resource = self._resource(key)
            if resource.cleanup is None:
                raise LiveSuiteError(f"resource {key!r} has no finalized cleanup request")
            expected = resource.cleanup
            refresh = expected.get("refresh")
            if operation["operationId"] != expected["operationId"] or (
                without_preconditions(request, refresh)
                != without_preconditions(expected["request"], refresh)
            ):
                raise LiveSuiteError(
                    f"{operation['operationId']} does not match the recorded cleanup for "
                    f"resource {key!r}"
                )
        creation: ResourceRecord | None = None
        if step["createsResource"] is not None:
            creation = self._prepare_resource(step["createsResource"])
        response = self._call(operation, request)
        creation_captures = (
            referenced_variables(step["createsResource"]) & set(step["capture"])
            if step["createsResource"] is not None
            else set()
        )
        for name in creation_captures:
            self.variables[name] = json_pointer(response, step["capture"][name])
        if creation is not None:
            self._finalize_resource(creation, step["createsResource"])
        if target is not None and target.lifecycle == "transient":
            target.consumed = True
        for name, pointer in step["capture"].items():
            if name in creation_captures:
                continue
            self.variables[name] = json_pointer(response, pointer)
        for key in step["cleansResources"]:
            self._resource(key).cleaned = True

    def _rotate_credentials(self, operation: Mapping[str, Any]) -> None:
        """Rotate the adapter's Agent session. The manager never sees the tokens,
        so they cannot reach captures, the ledger, or the report."""

        try:
            self.adapter.rotate_agent_session(operation)
        except Exception as exc:
            raise LiveSuiteError(
                f"{operation['plane']}/{operation['operationId']} credential rotation "
                f"failed: {type(exc).__name__}: {self._redact(exc)}"
            ) from exc

    def _wait(self, operation: Mapping[str, Any], step: Mapping[str, Any]) -> None:
        """Repeat one read until a captured value matches, within a bounded time."""

        wait = step["wait"]
        pointer = step["capture"][wait["capture"]]
        expected = self._resolve(wait["equals"])
        request = self._resolve(step["request"])
        self._validate_explicit_paths(request, operation["operationId"])
        deadline = self.clock() + wait["timeoutSeconds"]
        attempts = 0
        while True:
            attempts += 1
            response = self._call(operation, request)
            try:
                observed = json_pointer(response, pointer)
                last = json.dumps(observed, sort_keys=True)
            except LiveSuiteError:
                observed, last = None, "<unresolved>"
            else:
                if json_equal(observed, expected):
                    break
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise LiveSuiteError(
                    f"{operation['operationId']} wait for {wait['capture']} = "
                    f"{self._redact(json.dumps(expected, sort_keys=True))} timed out after "
                    f"{wait['timeoutSeconds']}s and {attempts} attempts; last observed "
                    f"{self._redact(last[:200])}"
                )
            self.sleep(min(wait["intervalSeconds"], remaining))
        for name, capture_pointer in step["capture"].items():
            self.variables[name] = json_pointer(response, capture_pointer)

    def _cleanup_request(self, cleanup: Mapping[str, Any]) -> dict[str, Any]:
        """Return the frozen cleanup request with its declared preconditions filled.

        The refresh read's response fills only the declared header and body
        fields. Path parameters and the query are the frozen target.
        """

        request = json.loads(json.dumps(cleanup["request"]))
        refresh = cleanup.get("refresh")
        if refresh is None:
            return request
        refresh_operation = self.operations[refresh["operationId"]]
        if refresh_operation["safety"] != "read-only":
            raise LiveSuiteError(
                f"cleanup refresh {refresh['operationId']} is not read-only"
            )
        self._validate_explicit_paths(refresh["request"], refresh["operationId"])
        response = self._call(refresh_operation, refresh["request"])
        for header, pointer in refresh["headers"].items():
            value = str(precondition_value(response, pointer))
            request["headers"] = {
                name: item
                for name, item in request["headers"].items()
                if name.lower() != header.lower()
            }
            request["headers"][header] = value
        for target, pointer in refresh["body"].items():
            set_json_pointer(
                request["body"], target, precondition_value(response, pointer)
            )
        if (
            request["pathParameters"] != cleanup["request"]["pathParameters"]
            or request["query"] != cleanup["request"]["query"]
        ):
            raise LiveSuiteError("cleanup refresh changed the frozen cleanup target")
        return request

    def cleanup(self) -> list[str]:
        failures: list[str] = []
        for resource in reversed(self.ledger.resources):
            if not resource.remaining:
                continue
            if resource.identifier is None or resource.cleanup is None:
                message = (
                    "creation outcome has no captured identifier; "
                    f"manually inspect run-prefixed resource {resource.name!r}"
                )
                resource.cleanup_error = message
                failures.append(f"{resource.kind}/{resource.name}: {message}")
                self.ledger.write()
                continue
            cleanup = resource.cleanup
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
                self.adapter.execute(operation, self._cleanup_request(cleanup))
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
                item.identifier or item.name
                for item in self.ledger.resources
                if item.remaining
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
        self._issued_tokens: list[str] = []

    def _session_tokens(self) -> tuple[str | None, str | None]:
        # The Connection owns the delegated session and may already have
        # refreshed it for an Agent-lane call, so read its current tokens.
        # The SDK has no public accessor for them; this harness owns the
        # connection it reads.
        connection = self.connection
        with connection._agent_lock:  # noqa: SLF001
            return (
                connection._agent_access_token,  # noqa: SLF001
                connection._agent_refresh_token,  # noqa: SLF001
            )

    def rotate_agent_session(self, operation: Mapping[str, Any]) -> None:
        from postgrip.agent.openapi import OperationId

        connection = self.connection
        # Serialize with the Connection's own automatic refresh.
        with connection._agent_refresh_lock:  # noqa: SLF001
            _, refresh_token = self._session_tokens()
            if not refresh_token:
                raise LiveSuiteError(
                    "credential step requires an Agent session refresh token "
                    "(POSTGRIP_AGENT_REFRESH_TOKEN)"
                )
            session = connection.openapi.request(
                OperationId(operation["operationId"]),
                {"refreshToken": refresh_token},
                path_parameters={},
                query={},
                headers={},
            )
            if not isinstance(session, dict) or not all(
                isinstance(session.get(name), str) and session[name]
                for name in ("accessToken", "refreshToken")
            ):
                raise LiveSuiteError(
                    "credential rotation response did not contain a new session"
                )
            self._issued_tokens.extend(
                (session["accessToken"], session["refreshToken"])
            )
            connection.configure_agent_auth(
                agent_id=session.get("agentId") or None,
                access_token=session["accessToken"],
                refresh_token=session["refreshToken"],
                access_expires_at=session.get("accessExpiresAt") or None,
            )

    def sensitive_values(self) -> Iterable[str]:
        current = [token for token in self._session_tokens() if token]
        return [*self._issued_tokens, *current]

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
        self,
        responses: Mapping[str, Any],
        failures: set[str] | None = None,
        *,
        sequences: Mapping[str, list[Any]] | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self.responses = responses
        self.failures = failures or set()
        # Successive responses per operation; the last one repeats.
        self.sequences = {
            name: list(items) for name, items in (sequences or {}).items()
        }
        self.calls: list[str] = []
        self.requests: list[tuple[str, Mapping[str, Any]]] = []
        self.access_token: str | None = None
        self.refresh_token = refresh_token
        self.sent_refresh_tokens: list[str] = []
        self.issued_tokens: list[str] = []

    def execute(self, operation: Mapping[str, Any], request: Mapping[str, Any]) -> Any:
        operation_id = operation["operationId"]
        self.calls.append(operation_id)
        self.requests.append((operation_id, request))
        if operation_id in self.failures:
            # Echo the current session token, as a careless error might.
            raise RuntimeError(f"injected failure {self.access_token or ''}".strip())
        sequence = self.sequences.get(operation_id)
        if sequence:
            return sequence.pop(0) if len(sequence) > 1 else sequence[0]
        return self.responses.get(operation_id)

    def rotate_agent_session(self, operation: Mapping[str, Any]) -> None:
        self.calls.append(operation["operationId"])
        if not self.refresh_token:
            raise RuntimeError("no refresh token")
        self.sent_refresh_tokens.append(self.refresh_token)
        generation = len(self.sent_refresh_tokens)
        self.access_token = f"access-secret-{generation}"
        self.refresh_token = f"refresh-secret-{generation}"
        self.issued_tokens.extend((self.access_token, self.refresh_token))

    def sensitive_values(self) -> Iterable[str]:
        return [*self.sent_refresh_tokens, *self.issued_tokens]


def expect_rejection(action: Callable[[], object], fragment: str, label: str) -> None:
    try:
        action()
    except LiveSuiteError as exc:
        if fragment not in str(exc):
            raise AssertionError(f"{label}: unexpected error: {exc}") from exc
    else:
        raise AssertionError(f"{label}: unexpectedly accepted")


def capability_self_test(
    base: dict[str, Any],
    base_inventory: Mapping[str, Any],
    ownership: dict[str, Any],
    directory: Path,
) -> None:
    """Fixture, wait, and credential steps; transient and reset-owned
    resources; and cleanup precondition refresh (live-suites design D3, D3a)."""

    def operation(
        operation_id: str, safety: str, *, credentials: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "operationId": operation_id,
            "plane": "agent",
            "safety": safety,
            "authLane": "public" if credentials else "management",
            "acceptedCredentials": credentials or ["postgrip-token"],
        }

    inventory = {
        "contractBundleDigest": "self-test",
        "operations": [
            *base_inventory["operations"],
            # Owned by no self-test tier: only fixture and wait steps name them.
            operation("getA", "read-only"),
            operation("createSession", "mutation"),
            operation("openSession", "protocol"),
            operation("reserveName", "mutation"),
            operation("refreshSession", "mutation", credentials=[REFRESH_CREDENTIAL]),
        ],
    }
    empty: dict[str, Any] = {
        "pathParameters": {},
        "query": {},
        "headers": {},
        "body": None,
        "streamBodyBase64": None,
    }
    responses = {"createA": {"id": "id-a"}, "createB": {"id": "id-b"}}
    disposable = {"POSTGRIP_LIVE_DISPOSABLE": "true"}
    runs = iter(range(1, 1000))

    def copy(value: Any) -> Any:
        return json.loads(json.dumps(value))

    def step(
        operation_id: str,
        *,
        path: Mapping[str, str] | None = None,
        target: str | None = None,
        creates: dict[str, Any] | None = None,
        capture: Mapping[str, str] | None = None,
        **modes: Any,
    ) -> dict[str, Any]:
        return {
            "operationId": operation_id,
            "request": {**empty, "pathParameters": dict(path or {})},
            "capture": dict(capture or {}),
            "resourceKey": target,
            "createsResource": creates,
            "cleansResources": [],
            **modes,
        }

    def with_steps(
        *extra: dict[str, Any], replace: int | None = None
    ) -> dict[str, Any]:
        scenario = copy(base)
        if replace is not None:
            scenario["steps"].pop(replace)
        scenario["steps"].extend(copy(list(extra)))
        return scenario

    def validate(scenario: dict[str, Any], tier: str = "nightly") -> None:
        validate_scenario(scenario, tier=tier, inventory=inventory, ownership=ownership)

    def manager(
        scenario: dict[str, Any],
        name: str,
        adapter: FakeAdapter,
        *,
        environ: Mapping[str, str] = disposable,
        allow_destructive: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> FixtureManager:
        return FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=adapter,
            environ=environ,
            ledger_path=directory / f"{name}.json",
            allow_destructive=allow_destructive,
            run_id=f"{next(runs):016x}",
            clock=clock,
            sleep=sleep,
        )

    def ledger(name: str) -> dict[str, Any]:
        return load_json(directory / f"{name}.json")

    a_path = {"id": "${var.a}"}

    # Fixture steps: any operation, repeated, under the same safety rules,
    # and never counted toward the tier's coverage.
    second_a = step(
        "createA",
        capture={"a2": "/id"},
        creates={
            "key": "a2",
            "kind": "fixture",
            "identifier": "${var.a2}",
            "name": "${runPrefix}-a2",
            "cleanup": {
                "operationId": "deleteA",
                "request": {**empty, "pathParameters": {"id": "${var.a2}"}},
            },
        },
        fixture=True,
    )
    second_a["request"]["body"] = {"name": "${runPrefix}-a2"}
    fixtures = with_steps(second_a, step("getA", path=a_path, target="a", fixture=True))
    validate(fixtures)
    if step_summary(fixtures) != "operations=3, fixtureSteps=2, waitSteps=0":
        raise AssertionError(f"fixture steps were counted: {step_summary(fixtures)}")
    fixture_adapter = FakeAdapter(
        responses, sequences={"createA": [{"id": "id-a"}, {"id": "id-a2"}]}
    )
    manager(fixtures, "fixtures", fixture_adapter).run()
    fixture_ledger = ledger("fixtures")
    if (
        fixture_adapter.calls[-3:] != ["deleteA", "deleteB", "deleteA"]
        or fixture_ledger["remainingIdentifiers"]
        or [item["role"] for item in fixture_ledger["operations"]]
        != ["counted", "counted", "counted", "fixture", "fixture"]
    ):
        raise AssertionError(
            "fixture steps were not run and cleaned like counted steps"
        )
    repeated = with_steps(step("createB", path={}, creates=None))
    expect_rejection(
        lambda: validate(repeated), "scenario repeats operations", "counted repeat"
    )
    uncovered = with_steps({**copy(base["steps"][2]), "fixture": True}, replace=2)
    expect_rejection(
        lambda: validate(uncovered), "missing=['inspect']", "fixture coverage"
    )
    expect_rejection(
        lambda: validate(with_steps(step("getA", fixture="yes"))),
        "fixture must be boolean",
        "fixture flag type",
    )
    unowned = with_steps(step("createB", fixture=True))
    expect_rejection(
        lambda: manager(unowned, "fixture-unowned", FakeAdapter(responses)).run(),
        "must target or create an explicitly recorded resource",
        "fixture mutation without a resource",
    )
    destructive = with_steps(step("deleteA", path=a_path, target="a", fixture=True))
    expect_rejection(
        lambda: manager(
            destructive,
            "fixture-guard",
            FakeAdapter(responses),
            allow_destructive=False,
        ).run(),
        "refusing destructive operation deleteA",
        "destructive fixture guard",
    )

    # Transient resources: consumed once by a protocol step, never cleaned.
    session = {
        "key": "session",
        "kind": "sandbox-session",
        "identifier": "${var.session}",
        "name": "${runPrefix}-session",
        "cleanup": None,
        "lifecycle": "transient",
    }
    create_session = step(
        "createSession",
        path=a_path,
        target="a",
        creates=session,
        capture={"session": "/id", "sessionTicket": "/ticket"},
        fixture=True,
    )
    open_session = step(
        "openSession",
        path={"sessionId": "${var.session}"},
        target="session",
        fixture=True,
    )
    open_session["request"]["query"] = {"ticket": "${var.sessionTicket}"}
    session_responses = {
        **responses,
        "createSession": {"id": "sess-1", "ticket": "ticket-secret"},
    }
    transient_adapter = FakeAdapter(session_responses)
    manager(
        with_steps(create_session, open_session), "transient", transient_adapter
    ).run()
    transient_ledger = ledger("transient")
    if (
        transient_ledger["consumedIdentifiers"] != ["sess-1"]
        or transient_ledger["remainingIdentifiers"]
        or transient_adapter.calls[-2:] != ["deleteB", "deleteA"]
        or "ticket-secret" in (directory / "transient.json").read_text()
    ):
        raise AssertionError(
            "a consumed transient resource was not reported as consumed"
        )
    manager(with_steps(create_session), "expired", FakeAdapter(session_responses)).run()
    expired_ledger = ledger("expired")
    if (
        expired_ledger["status"] != "passed"
        or expired_ledger["expiredIdentifiers"] != ["sess-1"]
        or expired_ledger["remainingIdentifiers"]
    ):
        raise AssertionError(
            "an unconsumed transient resource was reported as remaining"
        )
    expect_rejection(
        lambda: validate(with_steps(create_session, open_session, open_session)),
        "is already consumed",
        "second transient consumer",
    )
    expect_rejection(
        lambda: validate(
            with_steps(
                create_session,
                step(
                    "inspect",
                    path={"id": "${var.session}"},
                    target="session",
                    fixture=True,
                ),
            )
        ),
        "only a protocol step may consume it",
        "mutation consuming a transient",
    )
    cleans_transient = with_steps(
        create_session, {**copy(open_session), "cleansResources": ["session"]}
    )
    expect_rejection(
        lambda: validate(cleans_transient),
        "cannot clean transient resource 'session'",
        "cleaning a transient",
    )
    with_cleanup = copy(create_session)
    with_cleanup["createsResource"]["cleanup"] = copy(
        base["steps"][0]["createsResource"]["cleanup"]
    )
    expect_rejection(
        lambda: validate(with_steps(with_cleanup)),
        "must have a null cleanup",
        "transient with cleanup",
    )
    unattributed = copy(create_session)
    unattributed["resourceKey"] = None
    unattributed["request"]["pathParameters"] = {}
    expect_rejection(
        lambda: manager(
            with_steps(unattributed),
            "transient-unattributed",
            FakeAdapter(session_responses),
        ).run(),
        "does not contain its run-prefixed resource name",
        "unattributed transient",
    )
    seeded = copy(base)
    seeded["seedResources"] = [{**copy(session), "identifier": "sess-0"}]
    expect_rejection(
        lambda: validate(seeded),
        "seeded resources must use cleanup lifecycle",
        "seeded transient",
    )

    # Reset-owned resources: accepted only under a held stage lease.
    reserve = step(
        "reserveName",
        capture={"namespace": "/id"},
        creates={
            "key": "namespace",
            "kind": "namespace",
            "identifier": "${var.namespace}",
            "name": "${runPrefix}-ns",
            "cleanup": None,
            "lifecycle": "reset-owned",
        },
        fixture=True,
    )
    reserve["request"]["body"] = {"name": "${runPrefix}-ns"}
    reset_owned = with_steps(reserve)
    validate(reset_owned)  # --validate-only runs without a lease
    reset_responses = {**responses, "reserveName": {"id": "ns-1"}}
    expect_rejection(
        lambda: manager(reset_owned, "no-lease", FakeAdapter(reset_responses)),
        "refusing reset-owned resources",
        "reset-owned without a lease",
    )
    if (directory / "no-lease.json").exists():
        raise AssertionError("a refused reset-owned run wrote a ledger")
    expect_rejection(
        lambda: manager(
            reset_owned,
            "lease-not-disposable",
            FakeAdapter(reset_responses),
            environ={STAGE_LEASE_ENV: "1-2-1", "POSTGRIP_LIVE_DISPOSABLE": "false"},
        ),
        "refusing reset-owned resources",
        "reset-owned outside a disposable environment",
    )
    expect_rejection(
        lambda: manager(
            reset_owned,
            "bad-lease",
            FakeAdapter(reset_responses),
            environ={**disposable, STAGE_LEASE_ENV: "bad lease!"},
        ),
        "is not a stage-lease run ID",
        "malformed stage lease",
    )
    reset_adapter = FakeAdapter(reset_responses)
    manager(
        reset_owned,
        "reset-owned",
        reset_adapter,
        environ={**disposable, STAGE_LEASE_ENV: "123-456-1"},
    ).run()
    reset_ledger = ledger("reset-owned")
    if (
        reset_ledger["stageResetIdentifiers"] != ["ns-1"]
        or reset_ledger["remainingIdentifiers"]
        or reset_ledger["stageLease"] != "123-456-1"
        or reset_ledger["resources"][-1]["outcome"] != "left-for-stage-reset"
        or reset_adapter.calls[-2:] != ["deleteB", "deleteA"]
    ):
        raise AssertionError("a reset-owned resource was not left for the stage reset")

    # Credential steps: rotate the adapter's Agent session; tokens never reach
    # captures, the ledger, or the report.
    rotate = step("refreshSession", rotatesCredentials=True, fixture=True)
    # Rotate twice before the counted Agent call: the second rotation must
    # send the refresh token the first one returned.
    rotating = with_steps(rotate, rotate)
    rotating["steps"][2:] = [*rotating["steps"][3:], rotating["steps"][2]]
    if [item["operationId"] for item in rotating["steps"]][2:] != [
        "refreshSession",
        "refreshSession",
        "inspect",
    ]:
        raise AssertionError("credential scenario is not ordered as intended")
    credential_adapter = FakeAdapter(responses, refresh_token="refresh-secret-initial")
    manager(rotating, "credentials", credential_adapter).run()
    credential_text = (directory / "credentials.json").read_text()
    if credential_adapter.sent_refresh_tokens != [
        "refresh-secret-initial",
        "refresh-secret-1",
    ] or any(
        token in credential_text for token in credential_adapter.sensitive_values()
    ):
        raise AssertionError("rotated tokens were not applied or reached the ledger")
    failing_adapter = FakeAdapter(
        responses, failures={"inspect"}, refresh_token="refresh-secret-initial"
    )
    rotate_then_fail = with_steps(rotate)
    rotate_then_fail["steps"][2:] = [
        *rotate_then_fail["steps"][3:],
        rotate_then_fail["steps"][2],
    ]
    try:
        manager(rotate_then_fail, "credentials-failure", failing_adapter).run()
    except LiveSuiteError as exc:
        failure_text = str(exc) + (directory / "credentials-failure.json").read_text()
        if "access-secret-1" in failure_text or "[REDACTED]" not in failure_text:
            raise AssertionError("a rotated access token reached the report") from exc
    else:
        raise AssertionError("injected failure after rotation unexpectedly passed")
    if failing_adapter.calls[:4] != ["createA", "createB", "refreshSession", "inspect"]:
        raise AssertionError("the injected failure did not follow the rotation")
    expect_rejection(
        lambda: validate(with_steps(step("refreshSession", fixture=True))),
        "must be a credential step",
        "refresh without the credential marker",
    )
    supplied = copy(rotate)
    supplied["request"]["body"] = {
        "refreshToken": "${env.POSTGRIP_AGENT_REFRESH_TOKEN}"
    }
    expect_rejection(
        lambda: validate(with_steps(supplied)),
        "credential step request must be empty",
        "scenario-supplied refresh token",
    )
    expect_rejection(
        lambda: validate(
            with_steps({**copy(rotate), "capture": {"agentToken": "/accessToken"}})
        ),
        "credential step cannot capture",
        "captured session token",
    )
    expect_rejection(
        lambda: validate(
            with_steps(step("getA", rotatesCredentials=True, fixture=True))
        ),
        "must name an operation that accepts an Agent refresh token",
        "credential marker on another operation",
    )
    expect_rejection(
        lambda: manager(
            with_steps(rotate), "credentials-missing", FakeAdapter(responses)
        ).run(),
        "credential rotation failed",
        "rotation without a refresh token",
    )

    # Precondition refresh: a read just before the cleanup fills only its
    # declared header and body fields. The target path stays frozen.
    refreshed = copy(base)
    refreshed_cleanup = refreshed["steps"][0]["createsResource"]["cleanup"]
    refreshed_cleanup["request"]["body"] = {"force": True}
    refreshed_cleanup["refresh"] = {
        "operationId": "getA",
        "request": {**empty, "pathParameters": {"id": "${var.a}"}},
        "headers": {"If-Match": "/etag"},
        "body": {"/impactHash": "/impactHash"},
    }
    refresh_adapter = FakeAdapter(
        {
            **responses,
            "getA": {"etag": "etag-2", "impactHash": "hash-2", "id": "id-other"},
        }
    )
    manager(refreshed, "refresh", refresh_adapter).run()
    delete_request = refresh_adapter.requests[-1][1]
    if (
        refresh_adapter.calls[-2:] != ["getA", "deleteA"]
        or delete_request["pathParameters"] != {"id": "id-a"}
        or delete_request["headers"] != {"If-Match": "etag-2"}
        or delete_request["body"] != {"force": True, "impactHash": "hash-2"}
        or ledger("refresh")["remainingIdentifiers"]
    ):
        raise AssertionError(
            f"cleanup preconditions were not refreshed: {delete_request}"
        )
    path_fill = copy(refreshed)
    path_fill["steps"][0]["createsResource"]["cleanup"]["refresh"]["pathParameters"] = {
        "id": "/id"
    }
    expect_rejection(
        lambda: validate(path_fill), "must contain exactly", "refresh path fill"
    )
    mutating_refresh = copy(refreshed)
    mutating_refresh["steps"][0]["createsResource"]["cleanup"]["refresh"][
        "operationId"
    ] = "createB"
    expect_rejection(
        lambda: validate(mutating_refresh), "is not read-only", "mutating refresh"
    )
    credential_fill = copy(refreshed)
    credential_fill["steps"][0]["createsResource"]["cleanup"]["refresh"]["headers"] = {
        "Authorization": "/etag"
    }
    expect_rejection(
        lambda: validate(credential_fill),
        "cannot fill credential header",
        "credential header",
    )
    failed_refresh_adapter = FakeAdapter(responses, failures={"getA"})
    expect_rejection(
        lambda: manager(refreshed, "refresh-failure", failed_refresh_adapter).run(),
        "cleanup failures: fixture/id-a",
        "failed refresh",
    )
    if "deleteA" in failed_refresh_adapter.calls or ledger("refresh-failure")[
        "remainingIdentifiers"
    ] != ["id-a"]:
        raise AssertionError("a failed refresh did not leave its resource remaining")
    explicit = copy(refreshed)
    explicit["steps"].extend(
        [
            step(
                "getA", path=a_path, target="a", capture={"etag": "/etag"}, fixture=True
            ),
            {
                **step("deleteA", path=a_path, target="a", fixture=True),
                "cleansResources": ["a"],
            },
        ]
    )
    explicit["steps"][-1]["request"]["headers"] = {"If-Match": "${var.etag}"}
    explicit["steps"][-1]["request"]["body"] = {"force": True, "impactHash": "hash-1"}
    explicit_adapter = FakeAdapter({**responses, "getA": {"etag": "etag-1"}})
    manager(explicit, "refresh-explicit", explicit_adapter).run()
    if explicit_adapter.calls.count("deleteA") != 1:
        raise AssertionError(
            "an explicit cleanup with fresh preconditions was rejected"
        )

    # Wait steps: one read-only operation, bounded interval and total time.
    now = [0.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    def wait_step(timeout: int = 30, **overrides: Any) -> dict[str, Any]:
        value = step(
            "getA",
            path=a_path,
            target="a",
            capture={"status": "/status", "address": "/address"},
            wait={
                "capture": "status",
                "equals": "running",
                "intervalSeconds": 5,
                "timeoutSeconds": timeout,
            },
        )
        value["wait"].update(overrides)
        return value

    waiting = with_steps(wait_step())
    if step_summary(waiting) != "operations=3, fixtureSteps=0, waitSteps=1":
        raise AssertionError("a wait step was counted toward coverage")
    wait_adapter = FakeAdapter(
        responses,
        sequences={
            "getA": [
                {"status": "pending"},
                {"status": "pending"},
                {"status": "running", "address": "10.0.0.1"},
            ]
        },
    )
    wait_manager = manager(
        waiting, "wait", wait_adapter, clock=lambda: now[0], sleep=fake_sleep
    )
    wait_manager.run()
    if (
        wait_adapter.calls.count("getA") != 3
        or sleeps != [5, 5]
        or wait_manager.variables["address"] != "10.0.0.1"
        or ledger("wait")["operations"][-1]["role"] != "wait"
    ):
        raise AssertionError(
            f"wait step did not poll until its value matched: {sleeps}"
        )
    now[0], sleeps[:] = 0.0, []
    stalled_adapter = FakeAdapter(
        responses, sequences={"getA": [{"status": "pending"}]}
    )
    expect_rejection(
        lambda: manager(
            with_steps(wait_step(timeout=12)),
            "wait-timeout",
            stalled_adapter,
            clock=lambda: now[0],
            sleep=fake_sleep,
        ).run(),
        'timed out after 12s and 4 attempts; last observed "pending"',
        "wait timeout",
    )
    if sum(sleeps) != 12 or stalled_adapter.calls[-2:] != ["deleteB", "deleteA"]:
        raise AssertionError(f"wait exceeded its bound or skipped cleanup: {sleeps}")
    now[0] = 0.0
    expect_rejection(
        lambda: manager(
            with_steps(wait_step(timeout=5)),
            "wait-unresolved",
            FakeAdapter({**responses, "getA": {}}),
            clock=lambda: now[0],
            sleep=fake_sleep,
        ).run(),
        "last observed <unresolved>",
        "wait on an absent value",
    )
    mutating_wait = wait_step()
    mutating_wait["operationId"] = "createB"
    expect_rejection(
        lambda: validate(with_steps(mutating_wait)), "is not read-only", "mutating wait"
    )
    for overrides, fragment in (
        ({"intervalSeconds": 0}, "intervalSeconds must be an integer from 1 to 60"),
        (
            {"timeoutSeconds": WAIT_MAX_TIMEOUT_SECONDS + 1},
            "timeoutSeconds must be an integer",
        ),
        ({"intervalSeconds": True}, "intervalSeconds must be an integer"),
        ({"capture": "missing"}, "must name one of the step's captures"),
    ):
        bounded = with_steps(wait_step(**overrides))
        expect_rejection(
            functools.partial(validate, bounded),
            fragment,
            f"wait bounds {overrides}",
        )
    creating_wait = wait_step()
    creating_wait["cleansResources"] = ["a"]
    expect_rejection(
        lambda: validate(with_steps(creating_wait)),
        "cannot create or clean",
        "wait cleaning",
    )

    # Production smoke stays a fixed read-only allowlist: no step modes.
    production = load_json(ROOT / "test" / "live" / "production-smoke.json")
    real_inventory = load_json(INVENTORY_PATH)
    real_ownership = load_json(OWNERSHIP_PATH)["operations"]

    def validate_production(scenario: dict[str, Any]) -> None:
        validate_scenario(
            scenario,
            tier="production-smoke",
            inventory=real_inventory,
            ownership=real_ownership,
        )

    validate_production(production)
    for mode in ({"fixture": True}, {"fixture": False}):
        smoke = copy(production)
        smoke["steps"].append({**copy(smoke["steps"][0]), **mode})
        expect_rejection(
            functools.partial(validate_production, smoke),
            "production smoke steps cannot be fixture",
            f"production smoke {mode}",
        )


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
    validate_scenario(
        scenario, tier="nightly", inventory=inventory, ownership=ownership
    )
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
        # A decoy occurrence outside the target path must not satisfy ownership.
        mismatched_scenario["steps"][2]["request"]["body"] = {
            "relatedId": "${var.b}"
        }
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

        frozen_adapter = FakeAdapter({"createA": {"id": "id-a"}})
        frozen = FixtureManager(
            scenario=scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=frozen_adapter,
            environ={"POSTGRIP_LIVE_DISPOSABLE": "true"},
            ledger_path=Path(directory) / "frozen.json",
            allow_destructive=True,
            run_id="1122334455667788",
        )
        frozen.execute_step(scenario["steps"][0])
        frozen.variables["a"] = "id-overwritten"
        if frozen.cleanup():
            raise AssertionError("frozen cleanup unexpectedly failed")
        cleanup_request = frozen_adapter.requests[-1][1]
        if cleanup_request["pathParameters"]["id"] != "id-a":
            raise AssertionError("cleanup request changed after capture mutation")

        capture_failure_scenario = json.loads(json.dumps(scenario))
        capture_failure_scenario["steps"][0]["capture"] = {
            "unrelated": "/missing",
            "a": "/id",
        }
        capture_failure_adapter = FakeAdapter({"createA": {"id": "id-a"}})
        capture_failure = FixtureManager(
            scenario=capture_failure_scenario,
            inventory=inventory,
            ownership=ownership,
            tier="nightly",
            adapter=capture_failure_adapter,
            environ={"POSTGRIP_LIVE_DISPOSABLE": "true"},
            ledger_path=Path(directory) / "capture-failure.json",
            allow_destructive=True,
            run_id="2233445566778899",
        )
        try:
            capture_failure.run()
        except LiveSuiteError:
            pass
        else:
            raise AssertionError("missing secondary capture unexpectedly passed")
        capture_failure_ledger = load_json(
            Path(directory) / "capture-failure.json"
        )
        if (
            capture_failure_adapter.calls != ["createA", "deleteA"]
            or capture_failure_ledger["remainingIdentifiers"]
            or not capture_failure_ledger["resources"][0]["cleaned"]
        ):
            raise AssertionError(
                "created resource was not recorded before secondary capture failure"
            )

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
        capability_self_test(scenario, inventory, ownership, Path(directory))
    print("Live fixture-manager self-test passed")


def step_summary(scenario: Mapping[str, Any]) -> str:
    roles = [step_role(step) for step in scenario["steps"]]
    return (
        f"operations={roles.count('counted')}, fixtureSteps={roles.count('fixture')}, "
        f"waitSteps={roles.count('wait')}"
    )


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
                f"Live scenario validated: tier={args.tier}, {step_summary(scenario)}, "
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
        f"Live API suite passed: tier={args.tier}, {step_summary(scenario)}, "
        f"ledger={args.ledger}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
