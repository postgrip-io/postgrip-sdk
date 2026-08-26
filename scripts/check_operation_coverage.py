#!/usr/bin/env python3
"""Verify and report contract-derived documentation and test ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "test" / "operation-inventory.json"
OWNERSHIP = ROOT / "test" / "operation-tests.json"
REPORT_JSON = ROOT / "test" / "reports" / "operation-coverage.json"
REPORT_MARKDOWN = ROOT / "test" / "reports" / "operation-coverage.md"

GENERATED_FILES = {
    "agent": {
        "go": ROOT / "go" / "agent" / "client" / "openapi_operations.gen.go",
        "typescript": ROOT / "typescript" / "src" / "agent" / "generated" / "openapi.ts",
        "python": ROOT / "python" / "src" / "postgrip" / "agent" / "openapi.py",
    },
    "worker": {
        "go": ROOT / "go" / "worker" / "openapi_operations.gen.go",
        "typescript": ROOT / "typescript" / "src" / "worker" / "generated" / "openapi.ts",
        "python": ROOT / "python" / "src" / "postgrip" / "worker" / "openapi.py",
    },
    "service": {
        "go": ROOT / "go" / "service" / "openapi_operations.gen.go",
        "typescript": ROOT / "typescript" / "src" / "service" / "generated" / "openapi.ts",
        "python": ROOT / "python" / "src" / "postgrip" / "service" / "openapi.py",
    },
}


class CoverageError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CoverageError(f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_fixture(
    fixture: dict[str, Any], operation: dict[str, Any], relative_path: str
) -> None:
    required = {"schemaVersion", "operationId", "plane", "request", "response"}
    if set(fixture) != required or fixture.get("schemaVersion") != 1:
        raise CoverageError(f"{relative_path}: invalid fixture root")
    for field in ("operationId", "plane"):
        if fixture[field] != operation[field]:
            raise CoverageError(f"{relative_path}: {field} differs from inventory")
    request = fixture.get("request")
    if not isinstance(request, dict) or set(request) != {
        "pathParameters", "query", "headers", "body", "streamBodyBase64"
    }:
        raise CoverageError(f"{relative_path}: invalid request recording")
    if set(request["pathParameters"]) != set(operation["pathParameters"]):
        raise CoverageError(f"{relative_path}: path parameter ownership differs")
    if operation["protocol"] == "archive-stream":
        if not isinstance(request["streamBodyBase64"], str):
            raise CoverageError(f"{relative_path}: archive recording is missing bytes")
    elif request["streamBodyBase64"] is not None:
        raise CoverageError(f"{relative_path}: ordinary operation contains stream bytes")
    response = fixture.get("response")
    if not isinstance(response, dict) or set(response) != {"status", "headers", "body"}:
        raise CoverageError(f"{relative_path}: invalid response recording")
    if not isinstance(response["status"], int) or not 100 <= response["status"] <= 599:
        raise CoverageError(f"{relative_path}: invalid response status")


def build_report() -> dict[str, Any]:
    inventory = load(INVENTORY)
    ownership = load(OWNERSHIP)["operations"]
    digest = inventory["contractBundleDigest"]
    generated_contents = {
        plane: {
            language: path.read_text(encoding="utf-8")
            for language, path in paths.items()
        }
        for plane, paths in GENERATED_FILES.items()
    }
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for operation in inventory["operations"]:
        operation_id = operation["operationId"]
        plane = operation["plane"]
        owner = ownership.get(operation_id)
        if not isinstance(owner, dict):
            failures.append(f"{operation_id}: missing test ownership")
            continue
        page = ROOT / "docs" / "reference" / digest / plane / f"{operation_id}.md"
        documented = page.is_file()
        if not documented:
            failures.append(f"{operation_id}: missing immutable reference page")
        generated_languages = [
            language
            for language, content in generated_contents[plane].items()
            if operation_id in content
        ]
        sdk_generated = len(generated_languages) == len(GENERATED_FILES[plane])
        if not sdk_generated:
            failures.append(
                f"{operation_id}: generated ownership missing from "
                f"{sorted(set(GENERATED_FILES[plane]) - set(generated_languages))}"
            )
        fixture_relative = owner["fixture"]
        fixture_path = ROOT / "test" / "fixtures" / fixture_relative
        recorded_tested = fixture_path.is_file() and str(owner["mockTest"]).startswith("recorded-")
        if not recorded_tested:
            failures.append(f"{operation_id}: missing recorded fixture or runner ownership")
        else:
            try:
                validate_fixture(load(fixture_path), operation, f"test/fixtures/{fixture_relative}")
            except CoverageError as exc:
                failures.append(str(exc))
                recorded_tested = False
        curl = owner["curlEligible"]
        protocol_exception = owner["protocolException"] is not None
        if curl == protocol_exception:
            failures.append(f"{operation_id}: requires exactly one of cURL or protocol exception")
        if documented:
            page_text = page.read_text(encoding="utf-8")
            has_curl = "## cURL" in page_text and "curl \\\n" in page_text
            has_secure_bearer = (
                "--config" in page_text
                and 'header = "Authorization: Bearer ${POSTGRIP_TOKEN}"' in page_text
            )
            if curl and not (
                has_curl and (operation["authLane"] == "public" or has_secure_bearer)
            ):
                failures.append(f"{operation_id}: cURL-eligible page has no secure cURL")
            if protocol_exception and owner["protocolException"]["runner"] not in page_text:
                failures.append(f"{operation_id}: page omits its protocol runner")
        rows.append(
            {
                "operationId": operation_id,
                "plane": plane,
                "documented": documented,
                "sdkGenerated": sdk_generated,
                "generatedLanguages": generated_languages,
                "curl": curl,
                "protocolException": protocol_exception,
                "protocolRunner": (
                    owner["protocolException"]["runner"] if protocol_exception else None
                ),
                "recordedTested": recorded_tested,
                "recordedRunner": owner["mockTest"],
                "liveTest": owner["liveTest"],
            }
        )
    expected_ids = {row["operationId"] for row in inventory["operations"]}
    stale = sorted(set(ownership) - expected_ids)
    if stale:
        failures.append(f"stale ownership entries: {stale}")
    if failures:
        raise CoverageError("\n".join(failures))

    def count(field: str) -> int:
        return sum(bool(row[field]) for row in rows)

    summary = {
        "operations": len(rows),
        "documented": count("documented"),
        "sdkGenerated": count("sdkGenerated"),
        "curl": count("curl"),
        "protocolExceptions": count("protocolException"),
        "recordedTested": count("recordedTested"),
        # These are cadence ownership counts, not execution evidence. Live
        # workflows publish their ledgers as per-run artifacts; a static source
        # report must never imply that a configured environment actually ran.
        "nightlyOwned": sum(row["liveTest"] == "nightly" for row in rows),
        "preReleaseOwned": sum(row["liveTest"] == "pre-release" for row in rows),
        "productionSmokeOwned": sum(row["liveTest"] == "production-smoke" for row in rows),
    }
    planes = {
        plane: {
            "operations": sum(row["plane"] == plane for row in rows),
            "curl": sum(row["plane"] == plane and row["curl"] for row in rows),
            "protocolExceptions": sum(
                row["plane"] == plane and row["protocolException"] for row in rows
            ),
            "recordedTested": sum(
                row["plane"] == plane and row["recordedTested"] for row in rows
            ),
        }
        for plane in GENERATED_FILES
    }
    return {
        "schemaVersion": 1,
        "contractBundleDigest": digest,
        "summary": summary,
        "planes": planes,
        "operations": rows,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Unified SDK operation coverage",
        "",
        f"Contract bundle: `{report['contractBundleDigest']}`",
        "",
        "| Operations | Documented | SDK-generated | cURL | Protocol exceptions | "
        "Recorded-tested | Nightly-owned | Pre-release-owned | Production-smoke-owned |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {summary['operations']} | {summary['documented']} | "
            f"{summary['sdkGenerated']} | {summary['curl']} | "
            f"{summary['protocolExceptions']} | {summary['recordedTested']} | "
            f"{summary['nightlyOwned']} | {summary['preReleaseOwned']} | "
            f"{summary['productionSmokeOwned']} |"
        ),
        "",
        "| Plane | Operations | cURL | Protocol exceptions | Recorded-tested |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for plane, counts in report["planes"].items():
        lines.append(
            f"| {plane.title()} | {counts['operations']} | {counts['curl']} | "
            f"{counts['protocolExceptions']} | {counts['recordedTested']} |"
        )
    lines.extend(
        [
            "",
        "Every operation is documented, owned by generated clients in all three languages, "
        "and exercised by a recorded runner. Protocol exceptions are visible and are not "
        "counted as cURL coverage. Live columns are cadence ownership only; passing live "
        "evidence is carried by workflow cleanup-ledger artifacts.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="update checked-in reports")
    args = parser.parse_args()
    try:
        report = build_report()
    except (CoverageError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Operation coverage failed:\n{exc}")
        return 1
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown_text = markdown(report)
    if args.write:
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json_text, encoding="utf-8")
        REPORT_MARKDOWN.write_text(markdown_text, encoding="utf-8")
    else:
        expected = ((REPORT_JSON, json_text), (REPORT_MARKDOWN, markdown_text))
        differences = [
            str(path.relative_to(ROOT))
            for path, content in expected
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        if differences:
            print(f"Operation coverage reports differ: {differences}; run with --write")
            return 1
    summary = report["summary"]
    print(
        f"Operation coverage passed: {summary['operations']} operations, "
        f"{summary['curl']} cURL, {summary['protocolExceptions']} protocol exceptions, "
        f"{summary['recordedTested']} recorded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
