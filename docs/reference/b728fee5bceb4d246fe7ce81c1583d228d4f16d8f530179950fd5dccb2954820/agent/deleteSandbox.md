# Request sandbox deletion

`DELETE /api/v1/sandboxes/{sandboxId}` · `deleteSandbox` · Agent

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Agent contract `d9df466806e58ae32ab98f6622086d49749672258af902bdf3777a061fef28ff`

Sets desired state to deleted and returns 202 with the updated record. Teardown is asynchronous and completes when the assigned agent reports it.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Sandboxes` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
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

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Sandbox | `application/json` | `Sandbox` |
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

Sets desired state to deleted and returns 202 with the updated record. Teardown is asynchronous and completes when the assigned agent reports it.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SANDBOX_ID:?set POSTGRIP_SANDBOX_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  DELETE \
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
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "DELETE", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))


response, err := http.DefaultClient.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/sandboxes/" + encodeURIComponent(process.env.POSTGRIP_SANDBOX_ID ?? ""));

const response = await fetch(url, {
  method: "DELETE",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/sandboxes/' + urllib.parse.quote(os.environ['POSTGRIP_SANDBOX_ID'], safe='')
request = urllib.request.Request(endpoint, method='DELETE')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


with urllib.request.urlopen(request) as response:
    result = json.load(response)
```

## Related operations

- [connectSandboxSession](./connectSandboxSession.md) — Attach to an interactive session over WebSocket
- [createSandbox](./createSandbox.md) — Create a sandbox
- [createSandboxSession](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes
- [listWorkspaces](./listWorkspaces.md) — List uploaded workspaces

[Back to Agent index](./README.md)
