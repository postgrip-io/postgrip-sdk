#!/usr/bin/env python3
"""Generate deterministic, schema-validated per-operation recordings."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from jsonschema import Draft202012Validator, RefResolver

from _contracts import PLANES
from generate_api_docs import load_inputs, operations, request_body, resolve, sample


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "test" / "fixtures"


def parameter_value(document: dict[str, Any], parameter: dict[str, Any], operation_id: str) -> Any:
    name = parameter["name"]
    if name == "Idempotency-Key":
        return f"recorded-{operation_id}"
    if name == "If-Match":
        return '"revision:7"'
    value = sample(document, parameter.get("schema", {}))
    if value in (None, ""):
        return "recorded-value"
    return value


def success_response(
    document: dict[str, Any], operation: dict[str, Any]
) -> tuple[int, dict[str, str], Any, Any]:
    candidates = list(operation.get("responses", {}).items())
    selected = next(
        ((status, response) for status, response in candidates if str(status).startswith("2")),
        candidates[0],
    )
    status_text, raw = selected
    response = resolve(document, raw)
    content = response.get("content", {}) if isinstance(response, dict) else {}
    content_type = "application/json" if "application/json" in content else next(iter(content), None)
    media = content.get(content_type, {}) if content_type else {}
    schema = media.get("schema")
    body = media.get("example", sample(document, schema)) if media else None
    headers = {"X-Request-Id": f"req_{operation['operationId']}"}
    if body is not None and content_type:
        headers["Content-Type"] = content_type
    return int(status_text), headers, body, schema


def validate_instance(document: dict[str, Any], schema: Any, value: Any, label: str) -> None:
    if not schema:
        return
    validator = Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(document),
    )
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"{label} is not schema-valid: {detail}")


def render_tree(output: Path) -> int:
    contracts, _notes, ownership = load_inputs()
    count = 0
    for plane in PLANES:
        document = contracts[plane]
        for operation in operations(document):
            operation_id = operation["operationId"]
            path_parameters: dict[str, str] = {}
            query: dict[str, Any] = {}
            headers: dict[str, str] = {}
            for raw_parameter in operation["parameters"]:
                parameter = resolve(document, raw_parameter)
                value = parameter_value(document, parameter, operation_id)
                if not parameter.get("required") and value in ({}, []):
                    continue
                if parameter["in"] == "path":
                    path_parameters[parameter["name"]] = str(value)
                elif parameter["in"] == "query":
                    query[parameter["name"]] = value
                elif parameter["in"] == "header":
                    headers[parameter["name"]] = str(value)
            _content_type, request_schema, body = request_body(document, operation)
            stream_body = None
            if operation.get("x-postgrip-protocol") == "archive-stream":
                stream_body = base64.b64encode(b"recorded-workspace-archive").decode("ascii")
                body = None
            status, response_headers, response_body, response_schema = success_response(document, operation)
            if stream_body is None:
                validate_instance(document, request_schema, body, f"{operation_id} request")
            validate_instance(document, response_schema, response_body, f"{operation_id} response")
            fixture = {
                "schemaVersion": 1,
                "operationId": operation_id,
                "plane": plane,
                "request": {
                    "pathParameters": path_parameters,
                    "query": query,
                    "headers": headers,
                    "body": body,
                    "streamBodyBase64": stream_body,
                },
                "response": {
                    "status": status,
                    "headers": response_headers,
                    "body": response_body,
                },
            }
            target = output / ownership[operation_id]["fixture"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            count += 1
    return count


def compare(expected: Path, actual: Path) -> list[str]:
    expected_files = {path.relative_to(expected) for path in expected.rglob("*.json")}
    actual_files = {path.relative_to(actual) for path in actual.rglob("*.json")}
    failures = [f"missing fixture: {path}" for path in sorted(expected_files - actual_files)]
    failures.extend(f"stale fixture: {path}" for path in sorted(actual_files - expected_files))
    for relative in sorted(expected_files & actual_files):
        if (expected / relative).read_bytes() != (actual / relative).read_bytes():
            failures.append(f"fixture differs: {relative}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory) / "fixtures"
            count = render_tree(temporary)
            failures = compare(temporary, FIXTURES)
        if failures:
            print("Fixture drift detected:")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print(f"Recorded fixtures verified: {count} operations")
        return 0
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)
    count = render_tree(FIXTURES)
    print(f"Recorded fixtures generated: {count} operations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
