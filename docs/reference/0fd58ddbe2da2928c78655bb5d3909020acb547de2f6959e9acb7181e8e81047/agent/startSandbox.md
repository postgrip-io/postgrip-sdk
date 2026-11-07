# Request that a sandbox start

`POST /api/v1/sandboxes/{sandboxId}/start` · `startSandbox` · Agent

> Contract bundle `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

Sets desired state to running and returns 202. The returned record still carries the previous observed state; a sandbox is ready only once observedState is running and observedGeneration has caught up with generation. Starting a `failed` sandbox raises its generation, so its Agent tries again (see Sandbox.observedState).

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

Sets desired state to running and returns 202. The returned record still carries the previous observed state; a sandbox is ready only once observedState is running and observedGeneration has caught up with generation.

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
  POST \
  "${POSTGRIP_API_URL}/api/v1/sandboxes/${POSTGRIP_SANDBOX_ID}/start" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/sandboxes/" + url.PathEscape(os.Getenv("POSTGRIP_SANDBOX_ID")) + "/start")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))


client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/sandboxes/" + encodeURIComponent(process.env.POSTGRIP_SANDBOX_ID ?? "") + "/start");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/sandboxes/' + urllib.parse.quote(os.environ['POSTGRIP_SANDBOX_ID'], safe='') + '/start'
request = urllib.request.Request(endpoint, method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


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
