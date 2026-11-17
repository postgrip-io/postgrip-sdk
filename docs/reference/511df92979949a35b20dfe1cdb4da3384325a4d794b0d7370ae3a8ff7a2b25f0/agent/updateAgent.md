# Update Agent configuration

`PUT /api/v1/agents/{agentId}` · `updateAgent` · Agent

> Contract bundle `511df92979949a35b20dfe1cdb4da3384325a4d794b0d7370ae3a8ff7a2b25f0`
> Agent contract `24a728168d4329800c56fbd2230a94dcf06a76d92455906cf34f68a671b9465c`

Requires agent:admin. Updates name, logLevel and maintenanceWindow; omitted fields preserve current settings. Uses the existing Agent configuration lifecycle. Does not change trust, placement or signing identity.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agents` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:admin"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `agentId` | path | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `UpdateAgentConfigurationRequest`

```json
{
  "logLevel": "string",
  "maintenanceWindow": {
    "durationMinutes": 1,
    "enabled": true,
    "startMinute": 1,
    "timezone": "string"
  },
  "name": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Update Agent configuration | `application/json` | `AgentInventoryRecord` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
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
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Requires agent:admin. Updates name, logLevel and maintenanceWindow; omitted fields preserve current settings. Uses the existing Agent configuration lifecycle. Does not change trust, placement or signing identity.

- Use disposable tenant resources and restore settings or remove created resources after verification.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_AGENT_ID:?set POSTGRIP_AGENT_ID to a percent-encoded path value}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "logLevel": "string",
  "maintenanceWindow": {
    "durationMinutes": 1,
    "enabled": true,
    "startMinute": 1,
    "timezone": "string"
  },
  "name": "string"
}
POSTGRIP_JSON
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  PUT \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  "${POSTGRIP_API_URL}/api/v1/agents/${POSTGRIP_AGENT_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/agents/" + url.PathEscape(os.Getenv("POSTGRIP_AGENT_ID")))
if err != nil { return err }
body := strings.NewReader("{\"logLevel\":\"string\",\"maintenanceWindow\":{\"durationMinutes\":1,\"enabled\":true,\"startMinute\":1,\"timezone\":\"string\"},\"name\":\"string\"}")
request, err := http.NewRequestWithContext(ctx, "PUT", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/agents/" + encodeURIComponent(process.env.POSTGRIP_AGENT_ID ?? ""));

const response = await fetch(url, {
  method: "PUT",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"logLevel\":\"string\",\"maintenanceWindow\":{\"durationMinutes\":1,\"enabled\":true,\"startMinute\":1,\"timezone\":\"string\"},\"name\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/agents/' + urllib.parse.quote(os.environ['POSTGRIP_AGENT_ID'], safe='')
request = urllib.request.Request(endpoint, data='{"logLevel":"string","maintenanceWindow":{"durationMinutes":1,"enabled":true,"startMinute":1,"timezone":"string"},"name":"string"}'.encode(), method='PUT')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

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
- [listAgents](./listAgents.md) — List registered Agents

[Back to Agent index](./README.md)
