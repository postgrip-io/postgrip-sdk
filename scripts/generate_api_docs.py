#!/usr/bin/env python3
"""Generate immutable, detailed API reference pages from public contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
REFERENCE = ROOT / "docs" / "reference"
PLANES = ("agent", "worker", "service")
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def digest_bundle() -> tuple[str, dict[str, str]]:
    bundle = hashlib.sha256()
    per_plane: dict[str, str] = {}
    for plane in sorted(PLANES):
        path = CONTRACTS / f"{plane}-openapi.json"
        body = path.read_bytes()
        per_plane[plane] = hashlib.sha256(body).hexdigest()
        bundle.update(path.name.encode())
        bundle.update(b"\0")
        bundle.update(body)
        bundle.update(b"\0")
    return bundle.hexdigest(), per_plane


def load_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contracts = {
        plane: json.loads((CONTRACTS / f"{plane}-openapi.json").read_text(encoding="utf-8"))
        for plane in PLANES
    }
    notes = json.loads((ROOT / "test" / "operation-notes.json").read_text(encoding="utf-8"))["operations"]
    tests = json.loads((ROOT / "test" / "operation-tests.json").read_text(encoding="utf-8"))["operations"]
    return contracts, notes, tests


def resolve(document: dict[str, Any], value: Any) -> Any:
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    reference = value["$ref"]
    if not reference.startswith("#/"):
        return value
    current: Any = document
    for component in reference[2:].split("/"):
        current = current[component.replace("~1", "/").replace("~0", "~")]
    return current


def schema_name(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "—"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "oneOf" in schema:
        return " | ".join(schema_name(item) for item in schema["oneOf"])
    if "allOf" in schema:
        return " + ".join(schema_name(item) for item in schema["allOf"])
    value = schema.get("type", "object")
    if value == "array":
        return f"array<{schema_name(schema.get('items', {}))}>"
    if schema.get("format"):
        return f"{value} ({schema['format']})"
    return str(value)


def sample(document: dict[str, Any], schema: Any, seen: frozenset[str] = frozenset()) -> Any:
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference in seen:
            return {}
        return sample(document, resolve(document, schema), seen | {reference})
    if schema.get("allOf"):
        merged: dict[str, Any] = {}
        for item in schema["allOf"]:
            value = sample(document, item, seen)
            if isinstance(value, dict):
                merged.update(value)
        return merged
    for alternative in ("oneOf", "anyOf"):
        if schema.get(alternative):
            return sample(document, schema[alternative][0], seen)
    schema_type = schema.get("type")
    if not schema_type and "properties" in schema:
        schema_type = "object"
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = list(schema.get("required", []))
        selected = required or list(properties)[: min(3, len(properties))]
        value = {name: sample(document, properties[name], seen) for name in selected if name in properties}
        additional = schema.get("additionalProperties")
        if not value and int(schema.get("minProperties", 0)) > 0 and isinstance(additional, dict):
            value["recorded"] = sample(document, additional, seen)
        return value
    if schema_type == "array":
        count = max(int(schema.get("minItems", 1)), 1)
        return [sample(document, schema.get("items", {}), seen) for _ in range(count)]
    if schema_type == "integer":
        return max(int(schema.get("minimum", 1)), 1)
    if schema_type == "number":
        return max(float(schema.get("minimum", 1)), 1.0)
    if schema_type == "boolean":
        return True
    if schema.get("format") == "uuid":
        return "11111111-1111-4111-8111-111111111111"
    if schema.get("format") in {"date-time", "timestamp"}:
        return "2026-01-01T00:00:00Z"
    if schema.get("format") == "date":
        return "2026-01-01"
    pattern = schema.get("pattern")
    if pattern == "^[a-f0-9]{64}$":
        return "a" * 64
    if pattern == "^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$":
        return "recorded"
    if pattern == "^[A-Za-z_][A-Za-z0-9_]*$":
        return "RECORDED_VALUE"
    if pattern == "^(target|project):[0-9a-fA-F-]{36}$":
        return "project:11111111-1111-4111-8111-111111111111"
    if pattern in {"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$", "^[!-~]+$"}:
        return "recorded"
    return "string".ljust(max(int(schema.get("minLength", 0)), 6), "x")


def operations(document: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path, path_item in document["paths"].items():
        inherited = path_item.get("parameters", []) if isinstance(path_item, dict) else []
        for method in METHODS:
            operation = path_item.get(method) if isinstance(path_item, dict) else None
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            result.append({
                "path": path,
                "method": method.upper(),
                **operation,
                "parameters": inherited + operation.get("parameters", []),
            })
    return sorted(result, key=lambda item: item["operationId"])


def parameter_rows(document: dict[str, Any], operation: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    rows: list[str] = []
    parameters: list[dict[str, Any]] = []
    for raw in operation["parameters"]:
        parameter = resolve(document, raw)
        parameters.append(parameter)
        schema = resolve(document, parameter.get("schema", {}))
        value = sample(document, parameter.get("schema", {}))
        rendered = json.dumps(value, separators=(",", ":"))
        description = str(parameter.get("description", "")).replace("|", "\\|").replace("\n", " ") or "—"
        rows.append(
            f"| `{parameter.get('name', '')}` | {parameter.get('in', '')} | "
            f"{'yes' if parameter.get('required') else 'no'} | `{schema_name(parameter.get('schema', {}))}` | "
            f"`{rendered}` | {description} |"
        )
    return rows, parameters


def request_body(document: dict[str, Any], operation: dict[str, Any]) -> tuple[str | None, Any, Any]:
    raw = operation.get("requestBody")
    if not raw:
        return None, None, None
    body = resolve(document, raw)
    content = body.get("content", {})
    content_type = "application/json" if "application/json" in content else next(iter(content), None)
    if not content_type:
        return None, None, None
    media = content[content_type]
    example = media.get("example", sample(document, media.get("schema", {})))
    return content_type, media.get("schema", {}), example


def response_rows(document: dict[str, Any], operation: dict[str, Any]) -> tuple[list[str], Any]:
    rows: list[str] = []
    success_example: Any = None
    for status, raw in operation.get("responses", {}).items():
        response = resolve(document, raw)
        content = response.get("content", {}) if isinstance(response, dict) else {}
        media_type = "application/json" if "application/json" in content else next(iter(content), None)
        media = content.get(media_type, {}) if media_type else {}
        schema = media.get("schema", {})
        description = str(response.get("description", "")).replace("|", "\\|").replace("\n", " ") or "—"
        rows.append(f"| `{status}` | {description} | `{media_type or '—'}` | `{schema_name(schema)}` |")
        if success_example is None and str(status).startswith("2"):
            success_example = media.get("example", sample(document, schema)) if media else None
    return rows, success_example


def path_example(path: str) -> tuple[str, list[str]]:
    names = re.findall(r"\{([^}]+)\}", path)
    rendered = path
    for name in names:
        rendered = rendered.replace("{" + name + "}", "${POSTGRIP_" + snake(name).upper() + "}")
    return rendered, names


def snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


def shell_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).replace("'", "'\"'\"'")


def worker_create_curl_example() -> str:
    return r'''set +x
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or POSTGRIP_WORKER_URL}"
: "${POSTGRIP_WORKER_NAME:?set the pending Worker name}"
: "${POSTGRIP_WORKER_HOST:?set the Worker HTTPS origin}"
: "${POSTGRIP_BOOTSTRAP_STATE:?set an approved durable secret-state path}"
: "${POSTGRIP_WORKER_RECEIPT:?set a durable safe-receipt path}"
export POSTGRIP_WORKER_NAME POSTGRIP_WORKER_HOST POSTGRIP_BOOTSTRAP_STATE

# Exclusively persist caller-owned values and the replay key before POST.
python3 <<'PY'
import base64, hashlib, json, os, secrets, stat
path = os.path.abspath(os.environ["POSTGRIP_BOOTSTRAP_STATE"])
parent = os.path.dirname(path)
parent_mode = stat.S_IMODE(os.stat(parent).st_mode)
if parent_mode & 0o022 and not parent_mode & stat.S_ISVTX:
    raise SystemExit("bootstrap-state parent must not be group/world writable")
if os.path.lexists(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise SystemExit("existing bootstrap state must be a regular mode-0600 file")
    with open(path, encoding="utf-8") as stream:
        state = json.load(stream)
    if state.get("schemaVersion") != "postgrip.worker-create-curl/v1":
        raise SystemExit("existing bootstrap state has the wrong schema")
else:
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    request = {
        "name": os.environ["POSTGRIP_WORKER_NAME"],
        "host": os.environ["POSTGRIP_WORKER_HOST"].rstrip("/"),
        "autoShutdownOnRemoval": True,
        "bootstrap": {
            "enrollmentKey": encode(secrets.token_bytes(32)),
            "attestationBootstrapToken": encode(secrets.token_bytes(32)),
        },
    }
    canonical = json.dumps(request, separators=(",", ":"), sort_keys=True).encode()
    state = {
        "schemaVersion": "postgrip.worker-create-curl/v1",
        "idempotencyKey": "postgrip-worker-create-" + secrets.token_hex(16),
        "canonicalRequestDigest": hashlib.sha256(canonical).hexdigest(),
        "request": request,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, json.dumps(state, indent=2, sort_keys=True).encode() + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
PY

POSTGRIP_BODY_FILE="$(mktemp "$(dirname "${POSTGRIP_BOOTSTRAP_STATE}")/.postgrip-worker-request.XXXXXX")"
response_file="$(mktemp "$(dirname "${POSTGRIP_WORKER_RECEIPT}")/.postgrip-worker-response.XXXXXX")"
trap 'rm -f "${POSTGRIP_BODY_FILE}" "${response_file}"' EXIT
chmod 600 "${POSTGRIP_BODY_FILE}" "${response_file}"
POSTGRIP_IDEMPOTENCY_KEY="$(python3 - "${POSTGRIP_BOOTSTRAP_STATE}" "${POSTGRIP_BODY_FILE}" <<'PY'
import json, os, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    state = json.load(stream)
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(state["request"], stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(state["idempotencyKey"])
PY
)"

curl \
  --config \
  - \
  --fail-with-body --silent --show-error \
  --max-redirs 0 \
  --connect-timeout 5 --max-time 30 --max-filesize 1048576 \
  --request POST --header 'Content-Type: application/json' \
  --header "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --data-binary "@${POSTGRIP_BODY_FILE}" --output "${response_file}" \
  "${POSTGRIP_API_URL}/api/v1/workers" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF

# Atomically retain the safe Worker ID/ETag/expiries for the next bootstrap step.
python3 - "${response_file}" "${POSTGRIP_WORKER_RECEIPT}" <<'PY'
import json, os, stat, sys
source, target = sys.argv[1], os.path.abspath(sys.argv[2])
with open(source, encoding="utf-8") as stream:
    receipt = json.load(stream)
if not receipt.get("worker", {}).get("id") or not receipt.get("etag"):
    raise SystemExit("Worker response omitted its safe receipt")
os.chmod(source, 0o600)
os.replace(source, target)
directory = os.open(os.path.dirname(target), os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
python3 - "${POSTGRIP_WORKER_RECEIPT}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    receipt = json.load(stream)
print(json.dumps({"workerId": receipt["worker"]["id"], "etag": receipt["etag"], "bootstrap": receipt["bootstrap"]}, separators=(",", ":")))
PY'''


def curl_example(plane: str, operation: dict[str, Any], parameters: list[dict[str, Any]], body: Any, authenticated: bool) -> str:
    if operation["operationId"] == "createWorker":
        return worker_create_curl_example()
    path, names = path_example(operation["path"])
    lines = ["set +x", f'POSTGRIP_API_URL="${{POSTGRIP_{plane.upper()}_URL:-${{POSTGRIP_URL}}}}"']
    lines.append(': "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"')
    if authenticated:
        lines.append(': "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"')
    for name in names:
        env = "POSTGRIP_" + snake(name).upper()
        lines.append(f': "${{{env}:?set {env} to a percent-encoded path value}}"')
    query = []
    for parameter in parameters:
        if parameter.get("in") == "query" and parameter.get("required"):
            env = "POSTGRIP_" + snake(parameter["name"]).upper()
            lines.append(f': "${{{env}:?set {env} to a percent-encoded query value}}"')
            query.append(f"{parameter['name']}=${{{env}}}")
    if query:
        path += "?" + "&".join(query)
    required_headers = [
        parameter for parameter in parameters
        if parameter.get("in") == "header" and parameter.get("required")
    ]
    for parameter in required_headers:
        env = "POSTGRIP_" + snake(parameter["name"]).upper()
        lines.append(f': "${{{env}:?set {env} for this request}}"')
    if body is not None:
        lines.extend([
            'POSTGRIP_BODY_FILE="$(mktemp)"',
            'chmod 600 "${POSTGRIP_BODY_FILE}"',
            "trap 'rm -f \"${POSTGRIP_BODY_FILE}\"' EXIT",
            'cat >"${POSTGRIP_BODY_FILE}" <<\'POSTGRIP_JSON\'',
            json.dumps(body, indent=2, sort_keys=True),
            "POSTGRIP_JSON",
        ])
    command = ["curl"]
    if authenticated:
        command.extend(["--config", "-"])
    command.extend([
        "--fail-with-body", "--silent", "--show-error",
        "--request", operation["method"],
    ])
    if body is not None:
        command.extend(["--header", '"Content-Type: application/json"', "--data-binary", '"@${POSTGRIP_BODY_FILE}"'])
    for parameter in required_headers:
        env = "POSTGRIP_" + snake(parameter["name"]).upper()
        command.extend(["--header", f'"{parameter["name"]}: ${{{env}}}"'])
    command.append(f'"${{POSTGRIP_API_URL}}{path}"')
    formatted = " \\\n  ".join(command)
    lines.append(formatted)
    if authenticated:
        lines[-1] += " <<EOF\nheader = \"Authorization: Bearer ${POSTGRIP_TOKEN}\"\nEOF"
    return "\n".join(lines)


def expression_for_path(path: str, literal: Any, variable: Any) -> str:
    pieces: list[str] = []
    position = 0
    for match in re.finditer(r"\{([^}]+)\}", path):
        if match.start() > position:
            pieces.append(literal(path[position:match.start()]))
        pieces.append(variable("POSTGRIP_" + snake(match.group(1)).upper()))
        position = match.end()
    if position < len(path):
        pieces.append(literal(path[position:]))
    return " + ".join(pieces) if pieces else literal(path)


def http_examples(
    plane: str,
    operation: dict[str, Any],
    parameters: list[dict[str, Any]],
    body: Any,
    authenticated: bool,
) -> tuple[str, str, str]:
    path = operation["path"]
    method = operation["method"]
    body_json = json.dumps(body, separators=(",", ":"), sort_keys=True) if body is not None else ""
    auth_go = 'request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))' if authenticated else ""
    auth_ts = "Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`," if authenticated else ""
    auth_py = "request.add_header('Authorization', f\"Bearer {os.environ['POSTGRIP_TOKEN']}\")" if authenticated else ""
    go_path = expression_for_path(path, json.dumps, lambda env: f'url.PathEscape(os.Getenv("{env}"))')
    ts_path = expression_for_path(path, json.dumps, lambda env: f'encodeURIComponent(process.env.{env} ?? "")')
    py_path = expression_for_path(path, repr, lambda env: f"urllib.parse.quote(os.environ[{env!r}], safe='')")
    required_query = [
        parameter for parameter in parameters
        if parameter.get("in") == "query" and parameter.get("required")
    ]
    go_query = "\n".join(
        f'query.Set({json.dumps(parameter["name"])}, os.Getenv("POSTGRIP_{snake(parameter["name"]).upper()}"))'
        for parameter in required_query
    )
    if go_query:
        go_query = "\nquery := endpoint.Query()\n" + go_query + "\nendpoint.RawQuery = query.Encode()"
    ts_query = "\n".join(
        f'url.searchParams.set({parameter["name"]!r}, process.env.POSTGRIP_{snake(parameter["name"]).upper()} ?? "");'
        for parameter in required_query
    )
    py_query = ""
    if required_query:
        items = ", ".join(
            f'{parameter["name"]!r}: os.environ["POSTGRIP_{snake(parameter["name"]).upper()}"]'
            for parameter in required_query
        )
        py_query = f"\nquery = urllib.parse.urlencode({{{items}}})\nendpoint += '?' + query"
    required_headers = [
        parameter for parameter in parameters
        if parameter.get("in") == "header" and parameter.get("required")
    ]
    go_headers = "\n".join(
        f'request.Header.Set({json.dumps(parameter["name"])}, os.Getenv("POSTGRIP_{snake(parameter["name"]).upper()}"))'
        for parameter in required_headers
    )
    ts_headers = " ".join(
        f'{json.dumps(parameter["name"])}: process.env.POSTGRIP_{snake(parameter["name"]).upper()},'
        for parameter in required_headers
    )
    py_headers = "\n".join(
        f'request.add_header({parameter["name"]!r}, os.environ["POSTGRIP_{snake(parameter["name"]).upper()}"])'
        for parameter in required_headers
    )
    go_body = f'body := strings.NewReader({json.dumps(body_json)})' if body is not None else "var body io.Reader"
    go_content = 'request.Header.Set("Content-Type", "application/json")' if body is not None else ""
    go = f'''baseURL := os.Getenv("POSTGRIP_{plane.upper()}_URL")
if baseURL == "" {{ baseURL = os.Getenv("POSTGRIP_URL") }}
endpoint, err := url.Parse(baseURL + {go_path})
if err != nil {{ return err }}{go_query}
{go_body}
request, err := http.NewRequestWithContext(ctx, {json.dumps(method)}, endpoint.String(), body)
if err != nil {{ return err }}
{auth_go}
{go_content}
{go_headers}
client := &http.Client{{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error {{ return http.ErrUseLastResponse }},
}}
response, err := client.Do(request)'''
    ts_body = f",\n  body: {json.dumps(body_json)}" if body is not None else ""
    ts_content = '"Content-Type": "application/json",' if body is not None else ""
    ts = f'''const baseUrl = process.env.POSTGRIP_{plane.upper()}_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + {ts_path});
{ts_query}
const response = await fetch(url, {{
  method: {json.dumps(method)},
  redirect: "manual",
  headers: {{ {auth_ts} {ts_content} {ts_headers} }}{ts_body}
}});'''
    py_data = f", data={body_json!r}.encode()" if body is not None else ""
    py_content = "request.add_header('Content-Type', 'application/json')" if body is not None else ""
    py = f'''base_url = os.environ.get("POSTGRIP_{plane.upper()}_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + {py_path}{py_query}
request = urllib.request.Request(endpoint{py_data}, method={method!r})
{auth_py}
{py_content}
{py_headers}
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)'''
    return go, ts, py


def render_operation(
    plane: str,
    document: dict[str, Any],
    operation: dict[str, Any],
    note: dict[str, Any],
    test: dict[str, Any],
    bundle_digest: str,
    contract_digest: str,
    related: list[dict[str, Any]],
) -> str:
    parameter_lines, parameters = parameter_rows(document, operation)
    content_type, body_schema, body_example = request_body(document, operation)
    responses, success_example = response_rows(document, operation)
    credentials = operation.get("x-postgrip-accepted-credentials", [])
    scopes = operation.get("x-postgrip-required-scopes", [])
    authenticated = bool(credentials)
    protocol_exception = test.get("protocolException")
    curl = curl_example(plane, operation, parameters, body_example, authenticated) if test["curlEligible"] else ""
    go, ts, py = http_examples(plane, operation, parameters, body_example, authenticated)
    tags = operation.get("tags", [])
    lines = [
        f"# {note['summary']}", "",
        f"`{operation['method']} {operation['path']}` · `{operation['operationId']}` · {plane.title()}", "",
        f"> Contract bundle `{bundle_digest}`",
        f"> {plane.title()} contract `{contract_digest}`", "",
        operation.get("description") or note["behavior"], "",
        "## Operation", "",
        "| Field | Value |", "| --- | --- |",
        f"| Plane | `{plane}` |",
        f"| Resource tags | {', '.join(f'`{tag}`' for tag in tags) or '—'} |",
        f"| Operation class | `{operation['x-postgrip-operation-class']}` |",
        f"| Safety | `{operation['x-postgrip-safety']}` |",
        f"| Protocol | `{operation['x-postgrip-protocol']}` |",
        f"| Credentials | {', '.join(f'`{item}`' for item in credentials) or 'none'} |",
        f"| Required scopes | `{json.dumps(scopes, separators=(',', ':'))}` |",
        f"| Idempotency | `{operation['x-postgrip-idempotency']}` |",
        f"| Retry | `{operation['x-postgrip-retry']}` |",
        f"| Pagination | `{operation['x-postgrip-pagination']}` |", "",
        "## Parameters", "",
    ]
    if parameter_lines:
        lines.extend(["| Name | In | Required | Schema | Example | Description |", "| --- | --- | --- | --- | --- | --- |", *parameter_lines])
    elif operation["operationId"] == "createWorker":
        lines.extend([
            "", "## Typed SDK bootstrap workflow", "",
            "The generic raw snippets are intentionally omitted for this operation: a reliable caller must persist the bootstrap values and idempotency key before the request.",
            "Use the typed Go, TypeScript, or Python Worker client with the durable journal workflow in [`docs/worker-bootstrap.md`](../../../worker-bootstrap.md).", "",
        ])
    else:
        lines.append("This operation has no path or query parameters.")
    lines.extend(["", "## Request body", ""])
    if content_type:
        lines.extend([
            f"Content type: `{content_type}` · Schema: `{schema_name(body_schema)}`", "",
            "```json", json.dumps(body_example, indent=2, sort_keys=True), "```",
        ])
    else:
        lines.append("This operation has no request body.")
    lines.extend(["", "## Responses", "", "| Status | Meaning | Content type | Schema |", "| --- | --- | --- | --- |", *responses])
    if success_example is not None:
        lines.extend(["", "Illustrative success body:", "", "```json", json.dumps(success_example, indent=2, sort_keys=True), "```"])
    lines.extend([
        "", "Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.",
        "The `requestId` is safe to include in support and audit workflows; never log the bearer token.", "",
        "## Behavior and lifecycle", "", note["behavior"], "",
    ])
    if note["lifecycle"]:
        lines.extend(f"- {item}" for item in note["lifecycle"])
    else:
        lines.append("- No additional lifecycle constraint is recorded.")
    lines.extend(["", "## cURL", ""])
    if curl:
        lines.extend([
            "Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.", "",
            "```sh", curl, "```",
        ])
    elif protocol_exception:
        lines.extend([
            f"Stock cURL is not the conformance runner for this operation: {protocol_exception['reason']}", "",
            f"Runner: `{protocol_exception['runner']}` · Owner: `{protocol_exception['owner']}`.",
        ])
    else:
        lines.append("No cURL example is assigned.")
    if protocol_exception:
        lines.extend([
            "", "## Protocol adapter", "",
            "Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.",
            f"Use the typed {plane.title()} adapter and the `{protocol_exception['runner']}` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.", "",
        ])
    else:
        lines.extend([
            "", "## Equivalent raw HTTP", "",
            "These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.", "",
            "### Go", "", "```go", go, "```", "",
            "### TypeScript", "", "```ts", ts, "```", "",
            "### Python", "", "```python", py, "```", "",
        ])
    lines.extend(["## Related operations", ""])
    if related:
        lines.extend(f"- [{item['operationId']}](./{item['operationId']}.md) — {item.get('summary', item['operationId'])}" for item in related[:8])
    else:
        lines.append("- No operation shares this resource tag.")
    lines.extend(["", f"[Back to {plane.title()} index](./README.md)", ""])
    return "\n".join(lines)


def render_tree(output: Path) -> tuple[str, int]:
    contracts, notes, tests = load_inputs()
    bundle_digest, contract_digests = digest_bundle()
    inventory = json.loads((ROOT / "test" / "operation-inventory.json").read_text(encoding="utf-8"))
    if inventory["contractBundleDigest"] != bundle_digest:
        raise ValueError("operation inventory contract digest is stale")
    versioned = output / bundle_digest
    operation_count = 0
    root_lines = [
        "# PostGrip API reference", "",
        f"Immutable contract bundle: `{bundle_digest}`", "",
        "Every operation page is generated from the deployed public contracts and checked annotations.", "",
        "| Plane | Operations | Contract digest |", "| --- | ---: | --- |",
    ]
    for plane in PLANES:
        document = contracts[plane]
        plane_operations = operations(document)
        operation_count += len(plane_operations)
        plane_dir = versioned / plane
        plane_dir.mkdir(parents=True, exist_ok=True)
        tags: dict[str, list[dict[str, Any]]] = {}
        for operation in plane_operations:
            for tag in operation.get("tags", ["Other"]):
                tags.setdefault(tag, []).append(operation)
        plane_lines = [
            f"# {plane.title()} API", "",
            f"Contract digest: `{contract_digests[plane]}`",
            f"Bundle digest: `{bundle_digest}`", "",
        ]
        for tag in sorted(tags):
            plane_lines.extend([f"## {tag}", ""])
            for operation in tags[tag]:
                operation_id = operation["operationId"]
                plane_lines.append(f"- [`{operation_id}`](./{operation_id}.md) — {notes[operation_id]['summary']}")
            plane_lines.append("")
        (plane_dir / "README.md").write_text("\n".join(plane_lines), encoding="utf-8")
        for operation in plane_operations:
            operation_id = operation["operationId"]
            related = [
                candidate for candidate in plane_operations
                if candidate["operationId"] != operation_id
                and set(candidate.get("tags", [])) & set(operation.get("tags", []))
            ]
            page = render_operation(
                plane, document, operation, notes[operation_id], tests[operation_id],
                bundle_digest, contract_digests[plane], related,
            )
            (plane_dir / f"{operation_id}.md").write_text(page, encoding="utf-8")
        root_lines.append(f"| [{plane.title()}](./{plane}/README.md) | {len(plane_operations)} | `{contract_digests[plane]}` |")
    (versioned / "README.md").write_text("\n".join(root_lines) + "\n", encoding="utf-8")
    latest = output / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "index.html").write_text(
        "<!doctype html><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"refresh\" content=\"0; url=../{bundle_digest}/\">"
        f"<link rel=\"canonical\" href=\"../{bundle_digest}/\">"
        f"<title>PostGrip API reference {bundle_digest}</title>\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Versioned PostGrip API reference\n\n"
        f"- [Latest](./{bundle_digest}/README.md)\n"
        f"- Contract bundle: `{bundle_digest}`\n",
        encoding="utf-8",
    )
    return bundle_digest, operation_count


def compare_trees(expected: Path, actual: Path) -> list[str]:
    expected_files = {path.relative_to(expected) for path in expected.rglob("*") if path.is_file()}
    expected_bundles = {
        path.parts[0]
        for path in expected_files
        if path.parts and re.fullmatch(r"[a-f0-9]{64}", path.parts[0])
    }
    actual_files = {
        relative
        for path in actual.rglob("*")
        if path.is_file()
        for relative in (path.relative_to(actual),)
        if not (
            relative.parts
            and re.fullmatch(r"[a-f0-9]{64}", relative.parts[0])
            and relative.parts[0] not in expected_bundles
        )
    }
    failures = [f"missing generated documentation: {path}" for path in sorted(expected_files - actual_files)]
    failures += [f"stale generated documentation: {path}" for path in sorted(actual_files - expected_files)]
    for relative in sorted(expected_files & actual_files):
        if (expected / relative).read_bytes() != (actual / relative).read_bytes():
            failures.append(f"generated documentation differs: {relative}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory) / "reference"
            digest, count = render_tree(temporary)
            failures = compare_trees(temporary, REFERENCE)
        if failures:
            print("API documentation drift detected:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print(f"API documentation verified: {count} operations, bundle {digest[:12]}")
        return 0
    bundle, _contract_digests = digest_bundle()
    current = REFERENCE / bundle
    if current.exists():
        shutil.rmtree(current)
    digest, count = render_tree(REFERENCE)
    print(f"API documentation generated: {count} operations, bundle {digest[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
