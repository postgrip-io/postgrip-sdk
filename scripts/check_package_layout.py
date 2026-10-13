#!/usr/bin/env python3
"""Validate the unified repository has exactly one artifact per language."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent

# `export *`, `export * as name` and `export type *` re-exports in any legal
# spacing or position. Comments and string literals are blanked first, in one
# left-to-right pass, so neither can hide or fake a wildcard.
_WILDCARD_EXPORT = re.compile(r"(?<![\w$.])export\s+(?:type\s+)?\*")
_TYPESCRIPT_COMMENT_OR_STRING = re.compile(
    r"/\*.*?\*/|//[^\n]*|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`",
    re.DOTALL,
)


PLANES = ("agent", "worker", "service")
GO_MODULE = "github.com/postgrip-io/postgrip-agent-sdks/go"

# A module's role in the allowed-edge matrix: (kind, plane). Kinds are "root"
# (the facade composing planes), "adapter" (hand-written plane code), "gen"
# (generated plane bindings), "internal" (shared transport and helpers),
# "protocol" (Go runtime wire types) and "external" (anything outside the SDK).
Role = tuple[str, str]
_GO_IMPORT = re.compile(r'"(' + re.escape(GO_MODULE) + r'(?:/[^"]*)?)"')
_TYPESCRIPT_SPECIFIER = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)['"](\.{1,2}/[^'"]+)['"]"""
)


def edge_violation(source: Role, target: Role) -> str | None:
    """The rule an import from *source* to *target* breaks, or None when it is allowed."""

    source_kind, source_plane = source
    target_kind, target_plane = target
    if target_kind == "external" or source_kind == "root":
        return None
    if target_kind == "root":
        return "only the root facade composes planes; nothing imports it"
    if source_kind == "protocol":
        return None if target_kind == "protocol" else "protocol wire types import no plane or transport"
    if source_kind == "internal":
        return None if target_kind in ("internal", "protocol") else "transport imports no plane"
    if target_kind in ("internal", "protocol"):
        return None
    if target_plane != source_plane:
        return "planes never import another plane"
    if source_kind == "gen" and target_kind != "gen":
        return "generated bindings never import their plane's adapters"
    return None


def go_role(relative: Path) -> Role:
    """The role of a Go source file under go/."""

    parts = relative.parts
    if parts[0] in PLANES:
        return ("gen" if relative.name.endswith(".gen.go") else "adapter", parts[0])
    if parts[0] in ("internal", "protocol"):
        return (parts[0], "")
    return ("root", "")


def go_import_role(import_path: str) -> Role:
    """The role of an imported Go package; a package is never generated, only its files."""

    rest = import_path[len(GO_MODULE):].strip("/").split("/")
    if rest[0] in PLANES:
        return ("adapter", rest[0])
    if rest[0] in ("internal", "protocol"):
        return (rest[0], "")
    return ("root", "")


def go_imports(source: str) -> list[str]:
    return _GO_IMPORT.findall(source)


def typescript_role(relative: Path) -> Role:
    """The role of a TypeScript module path under typescript/src/."""

    parts = relative.parts
    if parts and parts[0] in PLANES:
        return ("gen" if "generated" in parts else "adapter", parts[0])
    if parts and parts[0] == "internal":
        return ("internal", "")
    return ("root", "")


def typescript_imports(relative: Path, source: str) -> list[Path]:
    """Relative module paths a TypeScript source under typescript/src/ imports, re-exports or loads."""

    targets = []
    for specifier in _TYPESCRIPT_SPECIFIER.findall(source):
        parts: list[str] = list(relative.parent.parts)
        for part in specifier.split("/"):
            if part == "..":
                if not parts:
                    break
                parts.pop()
            elif part != ".":
                parts.append(part)
        targets.append(Path(*parts))
    return targets


def python_role(module: str) -> Role:
    """The role of a dotted Python module name; names outside postgrip are external."""

    parts = module.split(".")
    if parts[0] != "postgrip":
        return ("external", "")
    if len(parts) > 1 and parts[1] in PLANES:
        generated = "generated" in parts[2:] or parts[-1] == "openapi"
        return ("gen" if generated else "adapter", parts[1])
    if len(parts) > 1 and parts[1] == "_internal":
        return ("internal", "")
    return ("root", "")


def python_imports(module: str, is_package: bool, source: str) -> list[str]:
    """Dotted modules a Python module imports, resolving relative imports and imported submodules."""

    package = module.split(".") if is_package else module.split(".")[:-1]
    targets = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (package[: len(package) - node.level + 1] if node.level else []) + (node.module or "").split(".")
            base_name = ".".join(part for part in base if part)
            # `from postgrip import worker` imports the worker package itself.
            targets.extend(f"{base_name}.{alias.name}" for alias in node.names if alias.name != "*")
    return targets


def import_edge_failures() -> list[str]:
    """Every import in the shipped Go, TypeScript and Python sources that breaks the edge matrix."""

    failures = []
    go_root = ROOT / "go"
    for path in sorted(go_root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        relative = path.relative_to(go_root)
        for imported in go_imports(path.read_text(encoding="utf-8")):
            rule = edge_violation(go_role(relative), go_import_role(imported))
            if rule:
                failures.append(f"go/{relative} imports {imported}: {rule}")
    ts_root = ROOT / "typescript" / "src"
    for path in sorted(ts_root.rglob("*.ts")):
        relative = path.relative_to(ts_root)
        for target in typescript_imports(relative, path.read_text(encoding="utf-8")):
            rule = edge_violation(typescript_role(relative), typescript_role(target))
            if rule:
                failures.append(f"typescript/src/{relative} imports {target}: {rule}")
    py_root = ROOT / "python" / "src"
    for path in sorted((py_root / "postgrip").rglob("*.py")):
        relative = path.relative_to(py_root)
        is_package = path.name == "__init__.py"
        module = ".".join(relative.parent.parts if is_package else relative.with_suffix("").parts)
        for imported in python_imports(module, is_package, path.read_text(encoding="utf-8")):
            rule = edge_violation(python_role(module), python_role(imported))
            if rule:
                failures.append(f"python/src/{relative} imports {imported}: {rule}")
    return failures


def wildcard_export_lines(source: str) -> list[int]:
    """Return the 1-based lines of TypeScript wildcard re-exports in *source*."""

    blanked = _TYPESCRIPT_COMMENT_OR_STRING.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), source)
    return [blanked.count("\n", 0, match.start()) + 1 for match in _WILDCARD_EXPORT.finditer(blanked)]


def edge_self_test_failures() -> list[str]:
    """Prove each edge rule in each language on generic sources."""

    failures = []

    def expect(label: str, rules: list[str | None], violates: bool) -> None:
        if any(rules) != violates:
            failures.append(f"{label}: got {rules}, want {'a violation' if violates else 'none'}")

    go = f'import (\n\t"context"\n\t"{GO_MODULE}/%s"\n)\n'
    for label, path, target, violates in (
        ("Go plane imports another plane", "worker/client.go", "service", True),
        ("Go generated imports its plane", "agent/client/openapi.gen.go", "agent/worker", True),
        ("Go transport imports a plane", "internal/transport/executor.go", "worker", True),
        ("Go protocol imports transport", "protocol/types.go", "internal/transport", True),
        ("Go plane imports the root", "agent/client/connection.go", "", True),
        ("Go plane imports its own subpackage", "agent/worker/dispatch.go", "agent/client", False),
        ("Go generated imports transport and protocol", "worker/openapi.gen.go", "internal/transport", False),
        ("Go root composes planes", "postgrip.go", "service", False),
    ):
        source = go % target if target else f'import "{GO_MODULE}"\n'
        expect(label, [edge_violation(go_role(Path(path)), go_import_role(i)) for i in go_imports(source)], violates)

    for label, path, source, violates in (
        ("TS plane imports another plane", "worker/client.ts", "import { X } from '../service/client.js';\n", True),
        ("TS re-export from another plane", "agent/index.ts", "export { Y } from '../worker/index.js';\n", True),
        ("TS dynamic import of another plane", "agent/client.ts", "const m = await import('../service/client.js');\n", True),
        ("TS side-effect import of another plane", "agent/client.ts", "import '../worker/client.js';\n", True),
        ("TS type import of the root", "service/client.ts", "import type { PostGripConfig } from '../client.js';\n", True),
        ("TS generated imports its adapter", "agent/generated/openapi.ts", "import { Connection } from '../connection.js';\n", True),
        ("TS transport imports a plane", "internal/transport.ts", "import { WorkerClient } from '../worker/client.js';\n", True),
        ("TS adapter imports generated and internal", "worker/client.ts",
         "import { OpenAPIClient } from './generated/openapi.js';\nimport { Executor } from '../internal/transport.js';\n", False),
        ("TS root composes planes", "client.ts", "import { WorkerClient } from './worker/client.js';\n", False),
    ):
        relative = Path(path)
        rules = [edge_violation(typescript_role(relative), typescript_role(t)) for t in typescript_imports(relative, source)]
        expect(label, rules, violates)

    for label, module, is_package, source, violates in (
        ("Python plane imports another plane", "postgrip.worker.client", False, "from ..service.client import ServiceClient\n", True),
        ("Python absolute import of another plane", "postgrip.agent.client", False, "import postgrip.worker.client\n", True),
        ("Python imports another plane package by name", "postgrip.service.client", False, "from .. import worker\n", True),
        ("Python plane imports the root", "postgrip.worker.client", False, "from ..client import PostGrip\n", True),
        ("Python generated imports its adapter", "postgrip.service.openapi", False, "from .client import ServiceClient\n", True),
        ("Python transport imports a plane", "postgrip._internal.transport", False, "from ..agent.errors import AgentAPIError\n", True),
        ("Python package init imports its adapter", "postgrip.worker", True, "from .client import WorkerClient\n", False),
        ("Python adapter imports generated and internal", "postgrip.worker.client", False,
         "from .openapi import OperationId\nfrom .._internal.transport import Executor\nimport json\n", False),
        ("Python root composes planes", "postgrip.client", False, "from .worker import WorkerClient\n", False),
    ):
        rules = [edge_violation(python_role(module), python_role(i)) for i in python_imports(module, is_package, source)]
        expect(label, rules, violates)
    return failures


def self_test() -> int:
    """Prove the wildcard and import-edge rules on generic sources; a clean tree alone proves nothing."""

    cases = {
        "export * from './client.js';\n": [1],
        "export * as generated from './generated/openapi.js';\n": [1],
        "export type * from './types.js';\n": [1],
        "const a = 1;\n  export * from './nested.js';\n": [2],
        "export { Client } from './client.js';\n": [],
        "export type { ClientConfig } from './client.js';\n": [],
        "export const value = 2 * 3;\n": [],
        "// export * from './client.js';\n": [],
        "/*\nexport * from './client.js';\n*/\nexport { A } from './a.js';\n": [],
        "export\n* from './split.js';\n": [1],
        "export type\n  *\n  from './split.js';\n": [1],
        "const a = 1; export * from './inline.js';\n": [1],
        "const text = 'export * from x';\n": [],
        "const url = 'https://example.test'; export * from './after-string.js';\n": [1],
        "const doc = `\nexport * from './template.js';\n`;\n": [],
        "module.export * 2;\n": [],
    }
    failures = [
        f"{source!r}: got {wildcard_export_lines(source)}, want {expected}"
        for source, expected in cases.items()
        if wildcard_export_lines(source) != expected
    ]
    failures.extend(edge_self_test_failures())
    if failures:
        print("check_package_layout self-test FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"check_package_layout self-test OK: {len(cases)} wildcard-export and 26 import-edge fixtures.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="check the rules against generic fixtures and exit")
    if parser.parse_args().self_test:
        return self_test()

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

    failures.extend(import_edge_failures())

    for source in sorted((ROOT / "typescript" / "src").rglob("*.ts")):
        for line in wildcard_export_lines(source.read_text(encoding="utf-8")):
            failures.append(f"TypeScript wildcard export: {source.relative_to(ROOT)}:{line}; list public names explicitly")

    if failures:
        print("Unified package layout FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Unified package layout OK: postgrip {version} (Go, npm, PyPI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
