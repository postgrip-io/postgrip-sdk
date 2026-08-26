#!/usr/bin/env python3
"""Build and inspect the three unified release artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
LIMITS = json.loads((ROOT / "test" / "release-limits.json").read_text(encoding="utf-8"))
INVENTORY = json.loads((ROOT / "test" / "operation-inventory.json").read_text(encoding="utf-8"))
DIGEST = INVENTORY["contractBundleDigest"]


class ReleaseError(ValueError):
    pass


def run(command: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, "GOWORK": "off"} if command[0] == "go" else os.environ.copy(),
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started
    if completed.returncode != 0:
        output = completed.stderr.strip() or completed.stdout.strip()
        raise ReleaseError(f"{' '.join(command)} failed: {output}")
    return completed, elapsed


def tracked(pattern: str) -> list[str]:
    completed, _ = run(["git", "ls-files", pattern], cwd=ROOT)
    return [line for line in completed.stdout.splitlines() if line]


def validate_metadata() -> dict[str, Any]:
    package = json.loads((ROOT / "typescript" / "package.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if package["version"] != VERSION or project["version"] != VERSION:
        raise ReleaseError("VERSION, npm, and PyPI versions differ")
    if package["name"] != "@postgrip/sdk" or project["name"] != "postgrip":
        raise ReleaseError("unified registry names differ from the design")
    manifests = {
        "go": tracked("*go.mod"),
        "typescript": tracked("*package.json"),
        "python": tracked("*pyproject.toml"),
    }
    expected = {
        "go": ["go/go.mod"],
        "typescript": ["typescript/package.json"],
        "python": ["python/pyproject.toml"],
    }
    if manifests != expected:
        raise ReleaseError(f"publishable manifests differ: {manifests!r}")
    publish_workflows = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / ".github" / "workflows").glob("publish-*.yml")
    )
    expected_workflows = [
        ".github/workflows/publish-go.yml",
        ".github/workflows/publish-python.yml",
        ".github/workflows/publish-typescript.yml",
    ]
    if publish_workflows != expected_workflows:
        raise ReleaseError(f"publishing workflows differ: {publish_workflows!r}")
    for ecosystem in ("go", "typescript", "python"):
        workflow = (ROOT / ".github" / "workflows" / f"publish-{ecosystem}.yml").read_text(encoding="utf-8")
        if f'      - "{ecosystem}/v*"' not in workflow:
            raise ReleaseError(f"{ecosystem} workflow has the wrong release tag")
        if "uses: ./.github/workflows/ci.yml" not in workflow:
            raise ReleaseError(f"{ecosystem} publishing does not require unified validation")
        if "environment:" not in workflow:
            raise ReleaseError(f"{ecosystem} publishing has no protected owner/deployment gate")
    digest_files = [
        ROOT / "go" / "agent" / "client" / "openapi_operations.gen.go",
        ROOT / "go" / "worker" / "openapi_operations.gen.go",
        ROOT / "go" / "service" / "openapi_operations.gen.go",
        ROOT / "typescript" / "src" / "agent" / "generated" / "openapi.ts",
        ROOT / "typescript" / "src" / "worker" / "generated" / "openapi.ts",
        ROOT / "typescript" / "src" / "service" / "generated" / "openapi.ts",
        ROOT / "python" / "src" / "postgrip" / "agent" / "openapi.py",
        ROOT / "python" / "src" / "postgrip" / "worker" / "openapi.py",
        ROOT / "python" / "src" / "postgrip" / "service" / "openapi.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in digest_files if DIGEST not in path.read_text(encoding="utf-8")]
    if missing:
        raise ReleaseError(f"contract bundle digest missing from {missing}")
    return {
        "version": VERSION,
        "contractBundleDigest": DIGEST,
        "manifests": manifests,
        "publishWorkflows": publish_workflows,
        "registryNames": {
            "go": "github.com/postgrip-io/postgrip-agent-sdks/go",
            "typescript": package["name"],
            "python": project["name"],
        },
    }


def inspect_go() -> dict[str, Any]:
    listed, elapsed = run(["go", "list", "./..."], cwd=ROOT / "go")
    files = tracked("go/**")
    source_bytes = sum((ROOT / path).stat().st_size for path in files)
    limits = LIMITS["go"]
    if len(files) > limits["maximumFiles"] or source_bytes > limits["maximumSourceBytes"]:
        raise ReleaseError("Go source module exceeds its reviewed artifact limit")
    module = (ROOT / "go" / "go.mod").read_text(encoding="utf-8")
    dependencies = re.findall(r"^require\s+([^\s]+)\s+v[^\s]+", module, flags=re.MULTILINE)
    block = re.search(r"require\s*\((.*?)\)", module, flags=re.DOTALL)
    if block:
        dependencies.extend(
            re.findall(r"^\s*([^\s]+)\s+v[^\s]+", block.group(1), flags=re.MULTILINE)
        )
    return {
        "files": len(files),
        "sourceBytes": source_bytes,
        "packages": len(listed.stdout.splitlines()),
        "directDependencies": dependencies,
        "inspectionSeconds": round(elapsed, 3),
    }


def inspect_typescript() -> dict[str, Any]:
    _, build_seconds = run(["bun", "run", "build"], cwd=ROOT / "typescript")
    packed, pack_seconds = run(["npm", "pack", "--dry-run", "--json"], cwd=ROOT / "typescript")
    payload = json.loads(packed.stdout)[0]
    paths = {item["path"] for item in payload["files"]}
    required = {
        "dist/index.js", "dist/index.d.ts",
        "dist/agent/index.js", "dist/agent/index.d.ts",
        "dist/worker/index.js", "dist/worker/index.d.ts",
        "dist/service/index.js", "dist/service/index.d.ts",
    }
    if not required <= paths:
        raise ReleaseError(f"npm artifact is missing {sorted(required - paths)}")
    limits = LIMITS["typescript"]
    if payload["entryCount"] > limits["maximumFiles"] or payload["unpackedSize"] > limits["maximumUnpackedBytes"]:
        raise ReleaseError("npm package exceeds its reviewed artifact limit")
    package = json.loads((ROOT / "typescript" / "package.json").read_text(encoding="utf-8"))
    return {
        "files": payload["entryCount"],
        "packedBytes": payload["size"],
        "unpackedBytes": payload["unpackedSize"],
        "directDependencies": sorted(package.get("dependencies", {})),
        "buildSeconds": round(build_seconds, 3),
        "inspectionSeconds": round(pack_seconds, 3),
    }


def inspect_python() -> dict[str, Any]:
    build_python = Path(os.environ.get("POSTGRIP_RELEASE_PYTHON", sys.executable))
    local_python = ROOT / "python" / ".venv" / "bin" / "python"
    if "POSTGRIP_RELEASE_PYTHON" not in os.environ and local_python.is_file():
        build_python = local_python
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        pip_probe = subprocess.run(
            [str(build_python), "-m", "pip", "--version"],
            capture_output=True,
            text=True,
        )
        if pip_probe.returncode == 0:
            command = [str(build_python), "-m", "pip", "wheel", "--no-deps", ".", "-w", str(output)]
        elif shutil.which("uv"):
            command = ["uv", "build", "--wheel", "--out-dir", str(output)]
        else:
            raise ReleaseError("Python artifact inspection requires pip or uv")
        _, build_seconds = run(command, cwd=ROOT / "python")
        wheels = list(output.glob("postgrip-*.whl"))
        if len(wheels) != 1:
            raise ReleaseError(f"expected one postgrip wheel, found {wheels}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            required = {
                "postgrip/__init__.py",
                "postgrip/agent/__init__.py",
                "postgrip/worker/__init__.py",
                "postgrip/service/__init__.py",
            }
            if not required <= names:
                raise ReleaseError(f"wheel is missing {sorted(required - names)}")
            metadata_name = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
            if metadata_name is None:
                raise ReleaseError("wheel has no package metadata")
            metadata = archive.read(metadata_name).decode("utf-8")
            if f"Name: postgrip\n" not in metadata or f"Version: {VERSION}\n" not in metadata:
                raise ReleaseError("wheel name or version differs")
        size = wheel.stat().st_size
        limits = LIMITS["python"]
        if len(names) > limits["maximumFiles"] or size > limits["maximumWheelBytes"]:
            raise ReleaseError("Python wheel exceeds its reviewed artifact limit")
    project = tomllib.loads((ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {
        "files": len(names),
        "wheelBytes": size,
        "directDependencies": project.get("dependencies", []),
        "buildSeconds": round(build_seconds, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecosystem", choices=("all", "go", "typescript", "python"), default="all")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report: dict[str, Any] = {"schemaVersion": 1, **validate_metadata(), "artifacts": {}}
        inspectors = {"go": inspect_go, "typescript": inspect_typescript, "python": inspect_python}
        selected = inspectors if args.ecosystem == "all" else {args.ecosystem: inspectors[args.ecosystem]}
        for ecosystem, inspector in selected.items():
            report["artifacts"][ecosystem] = inspector()
    except (ReleaseError, OSError, KeyError, ValueError, StopIteration, zipfile.BadZipFile) as exc:
        print(f"Release artifact check failed: {exc}")
        return 1
    if args.report:
        target = args.report if args.report.is_absolute() else ROOT / args.report
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    details = ", ".join(
        f"{name}={artifact.get('files', 0)} files" for name, artifact in report["artifacts"].items()
    )
    print(f"Release artifacts passed for {VERSION}: {details}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
