# List registered Agents

`GET /api/v1/agents` · `listAgents` · Agent

> Contract bundle `511df92979949a35b20dfe1cdb4da3384325a4d794b0d7370ae3a8ff7a2b25f0`
> Agent contract `24a728168d4329800c56fbd2230a94dcf06a76d92455906cf34f68a671b9465c`

Returns the organization’s visible Agents. Removed Agents are omitted. Requires agent:read.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agents` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | List registered Agents | `application/json` | `array<AgentInventoryRecord>` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
    "createdAt": "2026-01-01T00:00:00Z",
    "helperMaintenanceMode": true,
    "helperTrustState": "string",
    "id": "string",
    "logLevel": "string",
    "maintenanceWindow": {
      "durationMinutes": 1,
      "startMinute": 1,
      "timezone": "string"
    },
    "status": "string",
    "tenantId": "string",
    "trustState": "string",
    "updatedAt": "2026-01-01T00:00:00Z"
  }
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns the organization’s visible Agents. Removed Agents are omitted. Requires agent:read.

- Use disposable tenant resources and restore settings or remove created resources after verification.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/agents" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/agents")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "GET", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/agents");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/agents'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [createAgentEnrollmentKey](./createAgentEnrollmentKey.md) — Register an Agent enrollment key
- [deleteAgent](./deleteAgent.md) — Remove an Agent
- [enrollAgent](./enrollAgent.md) — Create an Agent by enrolling its host
- [getAgent](./getAgent.md) — Read an Agent
- [updateAgent](./updateAgent.md) — Update Agent configuration

[Back to Agent index](./README.md)
