#!/usr/bin/env python3
"""Validate generated operation inventory and human-owned annotations."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from _contracts import PLANES


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "test" / "operation-inventory.json"
TESTS_PATH = ROOT / "test" / "operation-tests.json"
NOTES_PATH = ROOT / "test" / "operation-notes.json"

OWNERSHIP_FIELDS = {
    "plane", "fixture", "cleanup", "mockTest", "liveTest",
    "curlEligible", "protocolException",
}
NOTE_FIELDS = {"summary", "behavior", "lifecycle"}
OPERATION_FIELDS = {
    "operationId", "plane", "method", "path", "operationClass", "authLane",
    "acceptedCredentials", "requiredScopes", "safety", "protocol", "signing",
    "idempotency", "pagination", "retry", "requestContentTypes",
    "responseContentTypes", "requestSchema", "responseSchema", "pathParameters",
}
LIVE_TIERS = {"nightly", "pre-release", "production-smoke"}
# x-postgrip-idempotency values; "optional" sends a caller's key without requiring one.
IDEMPOTENCY_VALUES = {"none", "optional", "required"}


class ValidationError(ValueError):
    pass


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=reject_duplicate_pairs)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def require_closed(value: dict[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValidationError(
            f"{location} fields differ: missing={sorted(expected-actual)}, unknown={sorted(actual-expected)}"
        )


def validate_checked_in_schemas() -> None:
    expectations = (
        ("operation-inventory.schema.json", "operation", OPERATION_FIELDS),
        ("operation-tests.schema.json", "ownership", OWNERSHIP_FIELDS),
        ("operation-notes.schema.json", "note", NOTE_FIELDS),
    )
    for filename, definition, fields in expectations:
        schema = load_json(ROOT / "test" / filename)
        if schema.get("additionalProperties") is not False:
            raise ValidationError(f"{filename}: root schema must be closed")
        definition_schema = schema.get("$defs", {}).get(definition, {})
        if definition_schema.get("additionalProperties") is not False:
            raise ValidationError(f"{filename}: {definition} schema must be closed")
        if set(definition_schema.get("required", [])) != fields:
            raise ValidationError(f"{filename}: required fields differ from checker")
        if set(definition_schema.get("properties", {})) != fields:
            raise ValidationError(f"{filename}: property fields differ from checker")


def validate(inventory: dict[str, Any], tests: dict[str, Any], notes: dict[str, Any]) -> None:
    require_closed(
        inventory,
        {"schemaVersion", "contractBundleDigest", "contractDigests", "operations"},
        "operation inventory",
    )
    if inventory["schemaVersion"] != 1:
        raise ValidationError("operation inventory schemaVersion must be 1")
    operations = inventory.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("operation inventory must contain operations")
    ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValidationError("inventory operation must be an object")
        require_closed(operation, OPERATION_FIELDS, "inventory operation")
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValidationError("inventory operationId must be non-empty")
        ids.append(operation_id)
        by_id[operation_id] = operation
        if operation.get("plane") not in PLANES:
            raise ValidationError(f"{operation_id}: invalid plane")
        if operation.get("operationClass") == "global-admin":
            raise ValidationError(f"{operation_id}: global administration leaked into public inventory")
        if operation.get("idempotency") not in IDEMPOTENCY_VALUES:
            raise ValidationError(f"{operation_id}: invalid idempotency {operation.get('idempotency')!r}")
    duplicates = sorted({operation_id for operation_id in ids if ids.count(operation_id) > 1})
    if duplicates:
        raise ValidationError(f"duplicate operation IDs: {duplicates}")

    for name, sidecar in (("operation-tests", tests), ("operation-notes", notes)):
        require_closed(sidecar, {"schemaVersion", "operations"}, name)
        if sidecar["schemaVersion"] != 1 or not isinstance(sidecar["operations"], dict):
            raise ValidationError(f"{name} has an invalid root")
        actual_ids = set(sidecar["operations"])
        expected_ids = set(by_id)
        if actual_ids != expected_ids:
            raise ValidationError(
                f"{name} operation IDs differ: missing={sorted(expected_ids-actual_ids)}, "
                f"stale={sorted(actual_ids-expected_ids)}"
            )

    for operation_id, ownership in tests["operations"].items():
        if not isinstance(ownership, dict):
            raise ValidationError(f"{operation_id}: ownership must be an object")
        require_closed(ownership, OWNERSHIP_FIELDS, f"{operation_id} ownership")
        if ownership["plane"] != by_id[operation_id]["plane"]:
            raise ValidationError(f"{operation_id}: ownership plane differs from inventory")
        for field in ("fixture", "mockTest"):
            if not isinstance(ownership[field], str) or not ownership[field].strip():
                raise ValidationError(f"{operation_id}: {field} must be non-empty")
        if ownership["cleanup"] not in {"none", "reverse-dependency"}:
            raise ValidationError(f"{operation_id}: invalid cleanup ownership")
        if ownership["liveTest"] not in LIVE_TIERS:
            raise ValidationError(f"{operation_id}: invalid live test tier")
        eligible = ownership["curlEligible"]
        exception = ownership["protocolException"]
        if not isinstance(eligible, bool):
            raise ValidationError(f"{operation_id}: curlEligible must be boolean")
        if eligible and exception is not None:
            raise ValidationError(f"{operation_id}: cURL-eligible operation cannot have an exception")
        if not eligible:
            if not isinstance(exception, dict):
                raise ValidationError(f"{operation_id}: cURL exception requires reason, owner, and runner")
            require_closed(exception, {"reason", "owner", "runner"}, f"{operation_id} exception")
            if any(not isinstance(exception[field], str) or not exception[field].strip() for field in exception):
                raise ValidationError(f"{operation_id}: cURL exception values must be non-empty")

    for operation_id, note in notes["operations"].items():
        if not isinstance(note, dict):
            raise ValidationError(f"{operation_id}: note must be an object")
        require_closed(note, NOTE_FIELDS, f"{operation_id} note")
        for field in ("summary", "behavior"):
            if not isinstance(note[field], str) or not note[field].strip():
                raise ValidationError(f"{operation_id}: {field} must be non-empty")
        if not isinstance(note["lifecycle"], list) or any(
            not isinstance(item, str) or not item.strip() for item in note["lifecycle"]
        ):
            raise ValidationError(f"{operation_id}: lifecycle must be a string array")


def self_test() -> None:
    validate_checked_in_schemas()
    inventory = load_json(INVENTORY_PATH)
    tests = load_json(TESTS_PATH)
    notes = load_json(NOTES_PATH)
    validate(inventory, tests, notes)
    stale = copy.deepcopy(tests)
    stale["operations"]["notAnOperation"] = next(iter(stale["operations"].values()))
    try:
        validate(inventory, stale, notes)
    except ValidationError:
        pass
    else:
        raise ValidationError("self-test failed to reject a stale operation")
    missing_exception = copy.deepcopy(tests)
    operation_id = next(
        key for key, value in missing_exception["operations"].items() if not value["curlEligible"]
    )
    missing_exception["operations"][operation_id]["protocolException"] = None
    try:
        validate(inventory, missing_exception, notes)
    except ValidationError:
        pass
    else:
        raise ValidationError("self-test failed to reject an unexplained cURL exception")
    unknown_idempotency = copy.deepcopy(inventory)
    unknown_idempotency["operations"][0]["idempotency"] = "sometimes"
    try:
        validate(unknown_idempotency, tests, notes)
    except ValidationError:
        pass
    else:
        raise ValidationError("self-test failed to reject an unknown idempotency value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print("Operation inventory checker self-test OK")
            return 0
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_openapi.py"),
             "--plane", "agent", "--language", "inventory", "--check"],
            cwd=ROOT,
            check=True,
        )
        validate_checked_in_schemas()
        validate(load_json(INVENTORY_PATH), load_json(TESTS_PATH), load_json(NOTES_PATH))
    except (ValidationError, subprocess.CalledProcessError) as exc:
        print(f"Operation inventory check failed: {exc}", file=sys.stderr)
        return 1
    print("Operation inventory and annotations OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
