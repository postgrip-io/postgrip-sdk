#!/usr/bin/env python3
"""Validate generated API-reference completeness and security invariants."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference"
PLANES = ("agent", "worker", "service")
REQUIRED_SECTIONS = (
    "## Operation",
    "## Parameters",
    "## Request body",
    "## Responses",
    "## Behavior and lifecycle",
    "## cURL",
    "## Related operations",
)


def main() -> int:
    inventory = json.loads(
        (ROOT / "test" / "operation-inventory.json").read_text(encoding="utf-8")
    )
    ownership = json.loads(
        (ROOT / "test" / "operation-tests.json").read_text(encoding="utf-8")
    )["operations"]
    bundle = inventory["contractBundleDigest"]
    versioned = REFERENCE / bundle
    failures: list[str] = []

    expected = {row["operationId"]: row for row in inventory["operations"]}
    if set(expected) != set(ownership):
        failures.append("operation inventory and test ownership keys differ")

    actual_pages: set[str] = set()
    for plane in PLANES:
        plane_dir = versioned / plane
        actual_pages.update(path.stem for path in plane_dir.glob("*.md") if path.name != "README.md")
    missing = sorted(set(expected) - actual_pages)
    extra = sorted(actual_pages - set(expected))
    failures.extend(f"missing operation page: {operation_id}" for operation_id in missing)
    failures.extend(f"unexpected operation page: {operation_id}" for operation_id in extra)

    for operation_id, row in expected.items():
        page_path = versioned / row["plane"] / f"{operation_id}.md"
        if not page_path.is_file():
            continue
        page = page_path.read_text(encoding="utf-8")
        label = f"{row['plane']}/{operation_id}"
        for section in REQUIRED_SECTIONS:
            if section not in page:
                failures.append(f"{label}: missing section {section}")
        for required in (
            bundle,
            inventory["contractDigests"][row["plane"]],
            operation_id,
            row["method"],
            row["path"],
        ):
            if required not in page:
                failures.append(f"{label}: missing contract fact {required}")

        test = ownership[operation_id]
        if operation_id == "createWorker":
            if "## Equivalent raw HTTP" in page:
                failures.append(f"{label}: unsafe generic raw bootstrap snippets were generated")
            for marker in ("## Typed SDK bootstrap workflow", "## Raw HTTP omission", "crash-safe pre-request journal"):
                if marker not in page:
                    failures.append(f"{label}: safe bootstrap guidance missing {marker!r}")
        if test["curlEligible"]:
            curl_block = extract_block(page, "sh")
            markers = ["set +x", 'POSTGRIP_API_URL=', "curl \\", "--fail-with-body"]
            if row["acceptedCredentials"]:
                markers.extend(
                    (
                        "POSTGRIP_TOKEN:?set POSTGRIP_TOKEN",
                        "--config \\",
                        'header = "Authorization: Bearer ${POSTGRIP_TOKEN}"',
                    )
                )
            for marker in markers:
                if marker not in curl_block:
                    failures.append(f"{label}: cURL example missing {marker!r}")
            if re.search(r"pgt_[A-Za-z0-9]", curl_block):
                failures.append(f"{label}: cURL contains a literal token")
            if re.search(r"--header\s+[\"']?Authorization:", curl_block, re.IGNORECASE):
                failures.append(f"{label}: bearer header is present in cURL argv")
            if "Content type: `application/json`" in page:
                for marker in ("mktemp", "chmod 600", "trap 'rm -f", '"@${POSTGRIP_BODY_FILE}"'):
                    if marker not in curl_block:
                        failures.append(f"{label}: protected request body missing {marker!r}")
            if operation_id == "createWorker":
                for marker in ('with open(source, "rb") as stream:', "os.fsync(stream.fileno())", "os.replace(source, target)"):
                    if marker not in curl_block:
                        failures.append(f"{label}: crash-safe receipt persistence missing {marker!r}")
        else:
            exception = test.get("protocolException")
            if not exception:
                failures.append(f"{label}: unexplained cURL gap")
            else:
                for value in (exception["reason"], exception["runner"], exception["owner"]):
                    if value not in page:
                        failures.append(f"{label}: protocol exception metadata is incomplete")
                if "## Equivalent raw HTTP" in page:
                    failures.append(f"{label}: protocol exception includes invalid raw HTTP")
        if "## Equivalent raw HTTP" in page:
            go_block = extract_block(page, "go")
            typescript_block = extract_block(page, "ts")
            python_block = extract_block(page, "python")
            if "http.DefaultClient.Do(request)" in go_block:
                failures.append(f"{label}: Go example follows redirects unsafely")
            for marker in (
                "CheckRedirect:",
                "http.ErrUseLastResponse",
                "client.Do(request)",
            ):
                if marker not in go_block:
                    failures.append(
                        f"{label}: Go example missing redirect guard {marker!r}"
                    )
            if 'redirect: "manual"' not in typescript_block:
                failures.append(f"{label}: TypeScript example follows redirects")
            if "urllib.request.urlopen" in python_block:
                failures.append(f"{label}: Python example follows redirects unsafely")
            for marker in (
                "class _NoRedirect(urllib.request.HTTPRedirectHandler):",
                "urllib.request.build_opener(_NoRedirect()).open(request)",
            ):
                if marker not in python_block:
                    failures.append(
                        f"{label}: Python example missing redirect guard {marker!r}"
                    )

    for package_readme in (ROOT / "go" / "README.md", ROOT / "typescript" / "README.md", ROOT / "python" / "README.md"):
        if bundle not in package_readme.read_text(encoding="utf-8"):
            failures.append(f"{package_readme.relative_to(ROOT)}: missing immutable reference link")

    latest = REFERENCE / "latest" / "index.html"
    if not latest.is_file() or bundle not in latest.read_text(encoding="utf-8"):
        failures.append("latest reference redirect does not target the contract bundle")

    if failures:
        print("API documentation validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    curl_count = sum(1 for item in ownership.values() if item["curlEligible"])
    print(
        f"API documentation validated: {len(expected)} operations, "
        f"{curl_count} cURL examples, bundle {bundle[:12]}"
    )
    return 0


def extract_block(page: str, language: str) -> str:
    match = re.search(rf"```{re.escape(language)}\n(.*?)\n```", page, re.DOTALL)
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
