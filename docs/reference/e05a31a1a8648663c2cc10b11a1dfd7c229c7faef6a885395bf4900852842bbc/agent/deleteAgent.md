# Remove an Agent

`DELETE /api/v1/agents/{agentId}` · `deleteAgent` · Agent

> Contract bundle `e05a31a1a8648663c2cc10b11a1dfd7c229c7faef6a885395bf4900852842bbc`
> Agent contract `24a728168d4329800c56fbd2230a94dcf06a76d92455906cf34f68a671b9465c`

Requires agent:admin. Revokes the Agent’s sessions and requests runtime shutdown through the existing removal lifecycle; later enrollment cannot restore a removed Agent. Worker resources have a separate lifecycle.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agents` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
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

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `204` | Remove an Agent | `—` | `object` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Requires agent:admin. Revokes the Agent’s sessions and requests runtime shutdown through the existing removal lifecycle; later enrollment cannot restore a removed Agent. Worker resources have a separate lifecycle.

- Use disposable tenant resources and restore settings or remove created resources after verification.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_AGENT_ID:?set POSTGRIP_AGENT_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  DELETE \
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
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "DELETE", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/agents/" + encodeURIComponent(process.env.POSTGRIP_AGENT_ID ?? ""));

const response = await fetch(url, {
  method: "DELETE",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/agents/' + urllib.parse.quote(os.environ['POSTGRIP_AGENT_ID'], safe='')
request = urllib.request.Request(endpoint, method='DELETE')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [createAgentEnrollmentKey](./createAgentEnrollmentKey.md) — Register an Agent enrollment key
- [enrollAgent](./enrollAgent.md) — Create an Agent by enrolling its host
- [getAgent](./getAgent.md) — Read an Agent
- [listAgents](./listAgents.md) — List registered Agents
- [updateAgent](./updateAgent.md) — Update Agent configuration

[Back to Agent index](./README.md)
