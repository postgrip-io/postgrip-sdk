#!/usr/bin/env python3
"""Validate the unified repository has exactly one artifact per language."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        failures.append(f"VERSION is not SemVer: {version!r}")

    expected_manifests = {
        "go.mod": [ROOT / "go" / "go.mod"],
        "package.json": [ROOT / "typescript" / "package.json"],
        "pyproject.toml": [ROOT / "python" / "pyproject.toml"],
    }
    for name, expected in expected_manifests.items():
        actual = sorted(ROOT.glob(f"*/{name}"))
        if actual != expected:
            failures.append(f"top-level {name} manifests: got {actual}, want {expected}")

    for legacy in ("protocol", "typescript-worker", "typescript-service", "python-worker", "python-service"):
        if (ROOT / legacy).exists():
            failures.append(f"obsolete artifact root still exists: {legacy}/")

    go_version = (ROOT / "go" / "version.go").read_text(encoding="utf-8")
    if f'const Version = "{version}"' not in go_version:
        failures.append("Go Version does not match VERSION")

    package = json.loads((ROOT / "typescript" / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "@postgrip/sdk":
        failures.append("npm package name is not @postgrip/sdk")
    if package.get("version") != version:
        failures.append("npm version does not match VERSION")
    expected_exports = {".", "./agent", "./worker", "./service"}
    if set(package.get("exports", {})) != expected_exports:
        failures.append("npm exports are not the root plus three singular planes")
    for subpath, entry in package.get("exports", {}).items():
        if set(entry) != {"types", "default"}:
            failures.append(f"npm export {subpath} lacks exact types/default conditions")

    project = tomllib.loads((ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if project.get("name") != "postgrip":
        failures.append("PyPI project name is not postgrip")
    if project.get("version") != version:
        failures.append("PyPI version does not match VERSION")
    typed_markers = list((ROOT / "python" / "src").rglob("py.typed"))
    if typed_markers != [ROOT / "python" / "src" / "postgrip" / "py.typed"]:
        failures.append(f"expected one root py.typed marker, got {typed_markers}")

    for plane in ("agent", "worker", "service"):
        if not (ROOT / "go" / plane).is_dir():
            failures.append(f"missing Go plane: {plane}")
        if not (ROOT / "typescript" / "src" / plane / "index.ts").is_file():
            failures.append(f"missing TypeScript plane entry: {plane}")
        if not (ROOT / "python" / "src" / "postgrip" / plane / "__init__.py").is_file():
            failures.append(f"missing Python plane entry: {plane}")

    go_root_import = '"github.com/postgrip-io/postgrip-agent-sdks/go"'
    for plane in ("agent", "worker", "service", "protocol"):
        for source in (ROOT / "go" / plane).rglob("*.go"):
            if go_root_import in source.read_text(encoding="utf-8"):
                failures.append(f"direct Go plane imports root facade: {source.relative_to(ROOT)}")
    for plane in ("agent", "worker", "service"):
        for source in (ROOT / "typescript" / "src" / plane).rglob("*.ts"):
            text = source.read_text(encoding="utf-8")
            if re.search(r"from ['\"]\.\./(?:client|index)\.js['\"]", text):
                failures.append(f"direct TypeScript plane imports root facade: {source.relative_to(ROOT)}")
        for source in (ROOT / "python" / "src" / "postgrip" / plane).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            if re.search(r"from \.\.(?:client|__init__) import", text):
                failures.append(f"direct Python plane imports root facade: {source.relative_to(ROOT)}")

    if failures:
        print("Unified package layout FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Unified package layout OK: postgrip {version} (Go, npm, PyPI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
