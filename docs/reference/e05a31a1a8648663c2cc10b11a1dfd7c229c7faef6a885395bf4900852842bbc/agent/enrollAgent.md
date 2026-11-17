# Create an Agent by enrolling its host

`POST /api/v1/agent/enroll` · `enrollAgent` · Agent

> Contract bundle `e05a31a1a8648663c2cc10b11a1dfd7c229c7faef6a885395bf4900852842bbc`
> Agent contract `24a728168d4329800c56fbd2230a94dcf06a76d92455906cf34f68a671b9465c`

Consumes the one-time enrollmentKey in the request and creates the Agent and its initial runtime session. The enrollment key is the credential, so no management bearer is sent. Generate the Ed25519 signing key on the host and send only signaturePublicKey. A used key is refused, and removed Agents cannot be restored by enrollment. Keep returned session credentials on that host.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agents` |
| Operation class | `agent-runtime` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `agent-enrollment-key` |
| Required scopes | `[]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `AgentEnrollmentRequest`

```json
{
  "enrollmentKey": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Create an Agent by enrolling its host | `application/json` | `AgentSessionResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "accessExpiresAt": "2026-01-01T00:00:00Z",
  "accessToken": "string",
  "agentId": "string",
  "refreshExpiresAt": "2026-01-01T00:00:00Z",
  "refreshToken": "string",
  "status": "string",
  "tenantId": "string",
  "tokenFamilyId": "string",
  "trustState": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Consumes the one-time enrollmentKey in the request and creates the Agent and its initial runtime session. The enrollment key is the credential, so no management bearer is sent. Generate the Ed25519 signing key on the host and send only signaturePublicKey. A used key is refused, and removed Agents cannot be restored by enrollment. Keep returned session credentials on that host.

- Use disposable tenant resources and restore settings or remove created resources after verification.

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
  "enrollmentKey": "string"
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
  "${POSTGRIP_API_URL}/api/v1/agent/enroll" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/agent/enroll")
if err != nil { return err }
body := strings.NewReader("{\"enrollmentKey\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/agent/enroll");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"enrollmentKey\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/agent/enroll'
request = urllib.request.Request(endpoint, data='{"enrollmentKey":"string"}'.encode(), method='POST')
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
- [getAgent](./getAgent.md) — Read an Agent
- [listAgents](./listAgents.md) — List registered Agents
- [updateAgent](./updateAgent.md) — Update Agent configuration

[Back to Agent index](./README.md)
