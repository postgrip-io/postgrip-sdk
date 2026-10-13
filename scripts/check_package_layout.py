#!/usr/bin/env python3
"""Validate the unified repository has exactly one artifact per language."""

from __future__ import annotations

import argparse
import ast
import codecs
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
TYPESCRIPT_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx")

# A module's role in the allowed-edge matrix: (kind, detail). Kinds are "root"
# (the facade composing planes), "adapter" and "gen" (hand-written and
# generated plane code, with the plane as detail), "internal" (shared transport
# and helpers), "protocol" (Go runtime wire types), "stdlib" (a standard
# library) and "external" (a third-party package, named in detail).
Role = tuple[str, str]
_GENERATED_HEADER = re.compile(r"\A[^\n]*Code generated [^\n]*DO NOT EDIT")
_GO_TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|`[^`]*`|\'(?:\\.|[^\'\\\n])*\'', re.DOTALL)
_GO_IMPORT_DECL = re.compile(r"\bimport\s*(\([^()]*\)|[\w.]*\s*S\d+S)")
_GO_PLACEHOLDER = re.compile(r"S(\d+)S")
_TYPESCRIPT_TOKEN = re.compile(
    r"/\*.*?\*/|//[^\n]*|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.DOTALL,
)
_TYPESCRIPT_IMPORT = re.compile(
    r"\bfrom\s*S(\d+)S|\bimport\s*\(\s*S(\d+)S|\bimport\s*S(\d+)S|\brequire\s*\(\s*S(\d+)S"
)
_TEMPLATE_INTERPOLATION = re.compile(r"\$\{((?:[^{}]|\{[^{}]*\})*)\}")
# Node's built-in modules, importable without the `node:` prefix.
NODE_BUILTINS = frozenset("""
assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel dns domain
events fs http http2 https inspector module net os path perf_hooks process punycode querystring readline repl
stream string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib
""".split())


def decode_escapes(literal: str) -> str:
    """The value of a Go interpreted or JavaScript string literal body, with escapes decoded."""

    literal = re.sub(r"\\u\{([0-9A-Fa-f]+)\}", lambda match: chr(int(match.group(1), 16)), literal)
    try:
        return codecs.decode(literal.encode("utf-8"), "unicode_escape").encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
        return literal


def is_generated(source: str) -> bool:
    """Whether *source* carries a generator's `Code generated ... DO NOT EDIT` first line."""

    return bool(_GENERATED_HEADER.match(source))


def edge_violation(source: Role, target: Role) -> str | None:
    """The rule an import from *source* to *target* breaks, or None when it is allowed."""

    source_kind, source_plane = source
    target_kind, target_plane = target
    if target_kind == "stdlib" or source_kind == "root":
        return None
    if target_kind == "external":
        return "generated bindings import only standard libraries and SDK modules" if source_kind == "gen" else None
    if target_kind == "root":
        return "only the root facade composes planes; nothing imports it"
    if source_kind == "protocol":
        return None if target_kind == "protocol" else "protocol wire types import no plane or transport"
    if source_kind == "internal":
        return None if target_kind in ("internal", "protocol") else "transport and other infrastructure import no plane"
    if target_kind in ("internal", "protocol"):
        return None
    if target_plane != source_plane:
        return "planes never import another plane"
    if source_kind == "gen" and target_kind != "gen":
        return "generated bindings never import their plane's adapters"
    return None


def go_role(relative: Path, source: str) -> Role:
    """The role of a Go source file under go/."""

    parts = relative.parts
    if parts[0] in PLANES:
        return ("gen" if is_generated(source) else "adapter", parts[0])
    if parts[0] == "protocol":
        return ("protocol", "")
    # Only the module's top-level files are the facade; any other directory is infrastructure.
    return ("root", "") if len(parts) == 1 else ("internal", "")


def go_import_role(import_path: str) -> Role:
    """The role of an imported Go package; a package is never generated, only its files."""

    if import_path != GO_MODULE and not import_path.startswith(GO_MODULE + "/"):
        first = import_path.split("/")[0]
        return ("external", import_path) if "." in first else ("stdlib", "")
    rest = import_path[len(GO_MODULE):].strip("/").split("/")
    if rest[0] in PLANES:
        return ("adapter", rest[0])
    if rest[0] == "protocol":
        return ("protocol", "")
    return ("root", "") if rest == [""] else ("internal", "")


def go_imports(source: str) -> list[str]:
    """Import paths of the import declarations in *source*, in either string form; comments are ignored."""

    literals: list[str] = []

    def mask(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith("/"):
            return re.sub(r"[^\n]", " ", token)
        # Every string becomes a placeholder, so text inside a string is never read as a declaration.
        literals.append(token[1:-1] if token.startswith("`") else decode_escapes(token[1:-1]))
        return f"S{len(literals) - 1}S"

    code = _GO_TOKEN.sub(mask, source)
    return [literals[int(index)] for declaration in _GO_IMPORT_DECL.findall(code) for index in _GO_PLACEHOLDER.findall(declaration)]


def typescript_role(relative: Path, source: str | None = None) -> Role:
    """The role of a TypeScript module under typescript/src/; *source* is its text when known."""

    parts = relative.parts
    if parts and parts[0] in PLANES:
        generated = is_generated(source) if source is not None else "generated" in parts
        return ("gen" if generated else "adapter", parts[0])
    # Only the facade entry modules are the root; any other module is infrastructure.
    return ("root", "") if len(parts) == 1 and Path(parts[0]).stem in ("client", "index") else ("internal", "")


def typescript_specifiers(source: str) -> list[str]:
    """Module specifiers *source* imports, re-exports or loads; comments and other strings are ignored."""

    strings: list[str] = []
    interpolated: list[str] = []

    def mask(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith("/"):
            return re.sub(r"[^\n]", " ", token)
        body = token[1:-1]
        if token.startswith("`"):
            # Template text is inert, but its ${...} expressions run.
            for expression in _TEMPLATE_INTERPOLATION.findall(body):
                interpolated.extend(typescript_specifiers(expression))
            if "${" in body:
                return " "
        strings.append(decode_escapes(body))
        return f"S{len(strings) - 1}S"

    code = _TYPESCRIPT_TOKEN.sub(mask, source)
    found = [strings[int(next(group for group in match if group))] for match in _TYPESCRIPT_IMPORT.findall(code)]
    return found + interpolated


def typescript_target_role(relative: Path, specifier: str, root: Path | None = None) -> Role:
    """The role of what *specifier*, imported by the module at *relative*, refers to."""

    if not specifier.startswith("."):
        builtin = specifier.startswith("node:") or specifier.split("/")[0] in NODE_BUILTINS
        return ("stdlib", "") if builtin else ("external", specifier)
    parts: list[str] = list(relative.parent.parts)
    for part in specifier.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    target = Path(*parts) if parts else Path()
    source = None
    if root is not None:
        stem = str(target)
        for suffix in (".js", ".mjs", ".cjs", ".jsx"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        for candidate in [*(Path(stem + ext) for ext in TYPESCRIPT_EXTENSIONS), Path(stem) / "index.ts"]:
            if (root / candidate).is_file():
                source = (root / candidate).read_text(encoding="utf-8")
                break
    return typescript_role(target, source)


def python_role(module: str, source: str | None = None) -> Role:
    """The role of a dotted Python module; *source* is its text when known."""

    parts = module.split(".")
    if parts[0] != "postgrip":
        top = parts[0]
        return ("stdlib", "") if top in sys.stdlib_module_names or top == "__future__" else ("external", top)
    if len(parts) > 1 and parts[1] in PLANES:
        generated = is_generated(source) if source is not None else ("generated" in parts[2:] or parts[-1] == "openapi")
        return ("gen" if generated else "adapter", parts[1])
    # Only the package itself and its facade module are the root; any other package is infrastructure.
    return ("root", "") if len(parts) == 1 or parts[1] in ("client", "__init__") else ("internal", "")


def python_imports(module: str, is_package: bool, source: str) -> list[str]:
    """Dotted modules a Python module imports, resolving relative, submodule and wildcard imports."""

    package = module.split(".") if is_package else module.split(".")[:-1]
    targets = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (package[: len(package) - node.level + 1] if node.level else []) + (node.module or "").split(".")
            base_name = ".".join(part for part in base if part)
            for alias in node.names:
                # `from pkg import *` depends on pkg; `from pkg import sub` may import the submodule.
                targets.append(base_name if alias.name == "*" else f"{base_name}.{alias.name}")
    return targets


def python_target_role(imported: str, root: Path | None = None) -> Role:
    """The role of an imported dotted name, reading the module it names when it is in the tree."""

    if root is not None and imported.split(".")[0] == "postgrip":
        parts = imported.split(".")
        for length in range(len(parts), 0, -1):
            for candidate in (root.joinpath(*parts[:length]).with_suffix(".py"), root.joinpath(*parts[:length], "__init__.py")):
                if candidate.is_file():
                    return python_role(".".join(parts[:length]), candidate.read_text(encoding="utf-8"))
    return python_role(imported)


def import_edge_failures() -> list[str]:
    """Every import in the shipped Go, TypeScript and Python sources that breaks the edge matrix."""

    failures = []
    go_root = ROOT / "go"
    for path in sorted(go_root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        relative = path.relative_to(go_root)
        text = path.read_text(encoding="utf-8")
        for imported in go_imports(text):
            rule = edge_violation(go_role(relative, text), go_import_role(imported))
            if rule:
                failures.append(f"go/{relative} imports {imported}: {rule}")
    ts_root = ROOT / "typescript" / "src"
    for path in sorted(p for ext in TYPESCRIPT_EXTENSIONS for p in ts_root.rglob(f"*{ext}")):
        relative = path.relative_to(ts_root)
        text = path.read_text(encoding="utf-8")
        for specifier in typescript_specifiers(text):
            rule = edge_violation(typescript_role(relative, text), typescript_target_role(relative, specifier, ts_root))
            if rule:
                failures.append(f"typescript/src/{relative} imports {specifier}: {rule}")
    py_root = ROOT / "python" / "src"
    for path in sorted((py_root / "postgrip").rglob("*.py")):
        relative = path.relative_to(py_root)
        is_package = path.name == "__init__.py"
        module = ".".join(relative.parent.parts if is_package else relative.with_suffix("").parts)
        text = path.read_text(encoding="utf-8")
        for imported in python_imports(module, is_package, text):
            rule = edge_violation(python_role(module, text), python_target_role(imported, py_root))
            if rule:
                failures.append(f"python/src/{relative} imports {imported}: {rule}")
    return failures


def wildcard_export_lines(source: str) -> list[int]:
    """Return the 1-based lines of TypeScript wildcard re-exports in *source*."""

    blanked = _TYPESCRIPT_COMMENT_OR_STRING.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), source)
    return [blanked.count("\n", 0, match.start()) + 1 for match in _WILDCARD_EXPORT.finditer(blanked)]


def edge_self_test_failures() -> tuple[list[str], int]:
    """Prove each edge rule in each language on generic sources."""

    failures = []
    header = "Code generated by fixture; DO NOT EDIT.\n"

    def expect(label: str, rules: list[str | None], violates: bool) -> None:
        if any(rules) != violates:
            failures.append(f"{label}: got {rules}, want {'a violation' if violates else 'none'}")

    go_cases = (
        ("Go plane imports another plane", "worker/client.go", f'import (\n\t"context"\n\t"{GO_MODULE}/service"\n)\n', True),
        ("Go raw-string import of another plane", "worker/client.go", f"import `{GO_MODULE}/service`\n", True),
        ("Go aliased import of another plane", "worker/client.go", f'import svc "{GO_MODULE}/service"\n', True),
        ("Go generated imports its plane", "agent/client/openapi.gen.go", f'// {header}import "{GO_MODULE}/agent/worker"\n', True),
        ("Go generated imports a third-party module", "worker/openapi.gen.go", f'// {header}import "github.com/example/http"\n', True),
        ("Go transport imports a plane", "internal/transport/executor.go", f'import "{GO_MODULE}/worker"\n', True),
        ("Go protocol imports transport", "protocol/types.go", f'import "{GO_MODULE}/internal/transport"\n', True),
        ("Go plane imports the root", "agent/client/connection.go", f'import "{GO_MODULE}"\n', True),
        ("Go escaped import path of another plane", "agent/client/connection.go", f'import "{GO_MODULE[:-1]}\\x6f/service"\n', True),
        ("Go helper directory imports a plane", "helpers/cache.go", f'import "{GO_MODULE}/agent/client"\n', True),
        ("Go comment and string mentioning another plane", "worker/client.go",
         f'// import "{GO_MODULE}/service"\nconst path = "{GO_MODULE}/service"\n', False),
        ("Go raw string containing an import statement", "worker/client.go",
         f'const doc = `import "{GO_MODULE}/service"`\n', False),
        ("Go plane imports its own subpackage and a third party", "agent/worker/dispatch.go",
         f'import (\n\t"{GO_MODULE}/agent/client"\n\t"golang.org/x/crypto/ed25519"\n)\n', False),
        ("Go generated imports transport and stdlib", "worker/openapi.gen.go",
         f'// {header}import (\n\t"net/http"\n\t"{GO_MODULE}/internal/transport"\n)\n', False),
        ("Go root composes planes", "postgrip.go", f'import "{GO_MODULE}/service"\n', False),
    )
    for label, path, source, violates in go_cases:
        role = go_role(Path(path), source)
        expect(label, [edge_violation(role, go_import_role(i)) for i in go_imports(source)], violates)

    ts_cases = (
        ("TS plane imports another plane", "worker/client.ts", "import { X } from '../service/client.js';\n", True),
        ("TS re-export from another plane", "agent/index.ts", "export { Y } from '../worker/index.js';\n", True),
        ("TS dynamic import of another plane", "agent/client.mts", "const m = await import('../service/client.js');\n", True),
        ("TS side-effect import with a comment", "agent/client.ts", "import/* reason */ '../worker/client.js';\n", True),
        ("TS type import of the root", "service/client.ts", "import type { PostGripConfig } from '../client.js';\n", True),
        ("TS generated imports its adapter", "agent/generated/openapi.ts", f"// {header}import {{ C }} from '../connection.js';\n", True),
        ("TS generated imports a package", "agent/generated/openapi.ts", f"// {header}import axios from 'axios';\n", True),
        ("TS transport imports a plane", "internal/transport.ts", "import { WorkerClient } from '../worker/client.js';\n", True),
        ("TS escaped specifier of another plane", "agent/client.ts", "import { W } from '\\x2e\\x2e/worker/client.js';\n", True),
        ("TS CommonJS require of another plane", "agent/client.cts", "const w = require('../worker/client.cjs');\n", True),
        ("TS import-equals require of another plane", "agent/client.cts", "import w = require('../worker/client.cjs');\n", True),
        ("TS dynamic import inside a template", "agent/client.ts", "const s = `${await import('../worker/client.js')}`;\n", True),
        ("TS helper directory imports a plane", "helpers/cache.ts", "import { W } from '../worker/client.js';\n", True),
        ("TS top-level helper imports a plane", "cache.ts", "import { W } from './worker/client.js';\n", True),
        ("TS generated imports a bare Node built-in", "agent/generated/openapi.ts", f"// {header}import {{ format }} from 'util';\n", False),
        ("TS comment and string mentioning another plane", "worker/client.ts",
         "// import '../service/client.js';\nconst s = \"import '../service/client.js'\";\n", False),
        ("TS adapter imports generated and internal", "worker/client.tsx",
         "import { OpenAPIClient } from './generated/openapi.js';\nimport { Executor } from '../internal/transport.js';\n", False),
        ("TS root composes planes", "client.ts", "import { WorkerClient } from './worker/client.js';\n", False),
    )
    for label, path, source, violates in ts_cases:
        relative = Path(path)
        role = typescript_role(relative, source)
        expect(label, [edge_violation(role, typescript_target_role(relative, s)) for s in typescript_specifiers(source)], violates)

    py_cases = (
        ("Python plane imports another plane", "postgrip.worker.client", False, "from ..service.client import ServiceClient\n", True),
        ("Python absolute import of another plane", "postgrip.agent.client", False, "import postgrip.worker.client\n", True),
        ("Python imports another plane package by name", "postgrip.service.client", False, "from .. import worker\n", True),
        ("Python wildcard import of another plane", "postgrip.agent.client", False, "from ..worker import *\n", True),
        ("Python plane imports the root", "postgrip.worker.client", False, "from ..client import PostGrip\n", True),
        ("Python generated module imports its adapter", "postgrip.service.administration_types", False,
         f"# {header}from .client import ServiceClient\n", True),
        ("Python generated imports a third-party package", "postgrip.worker.openapi", False, f"# {header}import requests\n", True),
        ("Python transport imports a plane", "postgrip._internal.transport", False, "from ..agent.errors import AgentAPIError\n", True),
        ("Python helper package imports a plane", "postgrip.helpers.cache", False, "from ..worker import WorkerClient\n", True),
        ("Python package init imports its adapter", "postgrip.worker", True, "from .client import WorkerClient\n", False),
        ("Python adapter imports generated, internal and third-party", "postgrip.agent.client", False,
         "from .openapi import OperationId\nfrom .._internal.transport import Executor\nimport cryptography\n", False),
        ("Python generated imports stdlib and its own generated module", "postgrip.worker.generated.openapi", False,
         f"# {header}from __future__ import annotations\nimport json\nfrom ..openapi import *\n", False),
        ("Python root composes planes", "postgrip.client", False, "from .worker import WorkerClient\n", False),
    )
    for label, module, is_package, source, violates in py_cases:
        role = python_role(module, source)
        expect(label, [edge_violation(role, python_target_role(i)) for i in python_imports(module, is_package, source)], violates)
    return failures, len(go_cases) + len(ts_cases) + len(py_cases)


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
    edge_failures, edge_fixtures = edge_self_test_failures()
    failures.extend(edge_failures)
    if failures:
        print("check_package_layout self-test FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"check_package_layout self-test OK: {len(cases)} wildcard-export and {edge_fixtures} import-edge fixtures.")
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

    for source in sorted(p for ext in TYPESCRIPT_EXTENSIONS for p in (ROOT / "typescript" / "src").rglob(f"*{ext}")):
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
