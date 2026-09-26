# Create a sandbox

`POST /api/v1/sandboxes` · `createSandbox` · Agent

> Contract bundle `aa3e67f82feac02dccb628c161e05394052a9041618fafcd1942c9afa034897e`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Records the desired sandbox and returns 201. Provisioning is asynchronous, so the returned record is not yet running. Names must be unique per tenant among live sandboxes.

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

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `SandboxCreateRequest`

```json
{
  "image": "string",
  "name": "recorded"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Sandbox | `application/json` | `Sandbox` |
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

Records the desired sandbox and returns 201. Provisioning is asynchronous, so the returned record is not yet running. Names must be unique per tenant among live sandboxes.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "image": "string",
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
  POST \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  "${POSTGRIP_API_URL}/api/v1/sandboxes" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/sandboxes")
if err != nil { return err }
body := strings.NewReader("{\"image\":\"string\",\"name\":\"recorded\"}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/sandboxes");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"image\":\"string\",\"name\":\"recorded\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/sandboxes'
request = urllib.request.Request(endpoint, data='{"image":"string","name":"recorded"}'.encode(), method='POST')
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
- [createSandboxSession](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [deleteSandbox](./deleteSandbox.md) — Request sandbox deletion
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes
- [listWorkspaces](./listWorkspaces.md) — List uploaded workspaces

[Back to Agent index](./README.md)
