# Update sandbox metadata

`PATCH /api/v1/sandboxes/{sandboxId}` · `updateSandbox` · Agent

> Contract bundle `e05a31a1a8648663c2cc10b11a1dfd7c229c7faef6a885395bf4900852842bbc`
> Agent contract `24a728168d4329800c56fbd2230a94dcf06a76d92455906cf34f68a671b9465c`

Updates name, labels or expiresAt. Omitted fields preserve stored values; at least one field is required. Labels replace user labels while preserving reserved Agent placement metadata; specifying postgrip.io/agent-id is refused. Names retain the create rules and tenant uniqueness. Expiration must be in the future and at most 24 hours after creation; expired or deleting/deleted sandboxes answer 404. Runtime identity, generation, image, resource limits and network policy stay unchanged.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Sandboxes` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:operate"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `sandboxId` | path | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `SandboxUpdateRequest`

```json
{
  "expiresAt": "2026-01-01T00:00:00Z",
  "labels": {},
  "name": "recorded"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Update sandbox metadata | `application/json` | `Sandbox` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "backend": "auto",
  "createdAt": "2026-01-01T00:00:00Z",
  "createdBy": "string",
  "desiredState": "running",
  "generation": 1,
  "id": "string",
  "image": "string",
  "isolationClass": "string",
  "name": "string",
  "networkPolicy": {
    "denyHostAccess": true,
    "internetEgress": true
  },
  "observedGeneration": 1,
  "observedState": "requested",
  "resourceLimits": {
    "cpus": 1.0,
    "diskBytes": 1,
    "memoryBytes": 1
  },
  "tenantId": "string",
  "updatedAt": "2026-01-01T00:00:00Z"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Updates name, labels or expiresAt. Omitted fields preserve stored values; at least one field is required. Labels replace user labels while preserving reserved Agent placement metadata; specifying postgrip.io/agent-id is refused. Names retain the create rules and tenant uniqueness. Expiration must be in the future and at most 24 hours after creation; expired or deleting/deleted sandboxes answer 404. Runtime identity, generation, image, resource limits and network policy stay unchanged.

- Use disposable tenant resources and restore settings or remove created resources after verification.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SANDBOX_ID:?set POSTGRIP_SANDBOX_ID to a percent-encoded path value}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "expiresAt": "2026-01-01T00:00:00Z",
  "labels": {},
  "name": "recorded"
}
POSTGRIP_JSON
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  PATCH \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  "${POSTGRIP_API_URL}/api/v1/sandboxes/${POSTGRIP_SANDBOX_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/sandboxes/" + url.PathEscape(os.Getenv("POSTGRIP_SANDBOX_ID")))
if err != nil { return err }
body := strings.NewReader("{\"expiresAt\":\"2026-01-01T00:00:00Z\",\"labels\":{},\"name\":\"recorded\"}")
request, err := http.NewRequestWithContext(ctx, "PATCH", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")

client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/sandboxes/" + encodeURIComponent(process.env.POSTGRIP_SANDBOX_ID ?? ""));

const response = await fetch(url, {
  method: "PATCH",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"expiresAt\":\"2026-01-01T00:00:00Z\",\"labels\":{},\"name\":\"recorded\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/sandboxes/' + urllib.parse.quote(os.environ['POSTGRIP_SANDBOX_ID'], safe='')
request = urllib.request.Request(endpoint, data='{"expiresAt":"2026-01-01T00:00:00Z","labels":{},"name":"recorded"}'.encode(), method='PATCH')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [connectSandboxSession](./connectSandboxSession.md) — Attach to an interactive session over WebSocket
- [createSandbox](./createSandbox.md) — Create a sandbox
- [createSandboxSession](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [deleteSandbox](./deleteSandbox.md) — Request sandbox deletion
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes

[Back to Agent index](./README.md)
