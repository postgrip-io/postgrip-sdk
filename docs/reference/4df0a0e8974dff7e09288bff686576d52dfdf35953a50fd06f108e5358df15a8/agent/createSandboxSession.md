# Mint a single-use ticket for a sandbox stream

`POST /api/v1/sandboxes/{sandboxId}/sessions` · `createSandboxSession` · Agent

> Contract bundle `4df0a0e8974dff7e09288bff686576d52dfdf35953a50fd06f108e5358df15a8`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Creates a pending pty, exec, or port session and returns its ticket exactly once -- only a hash of it is stored. The ticket is short-lived and is redeemed against the connect operation. The sandbox must already be running. Port sessions require an advertised port-stream-capable agent and a TCP guest port that is already published by the sandbox. Pending and connected sessions are limited to 20 per tenant, 10 per agent, and 5 per sandbox; a limit breach returns 429.

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

Content type: `application/json` · Schema: `CreateSandboxSessionRequest`

```json
{
  "columns": 80,
  "kind": "pty",
  "rows": 24
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Single-use relay ticket | `application/json` | `CreateSandboxSessionResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "expiresAt": "2026-01-01T00:00:00Z",
  "id": "string",
  "ticket": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Creates a pending pty, exec, or port session and returns its ticket exactly once -- only a hash of it is stored. The ticket is short-lived and is redeemed against the connect operation. The sandbox must already be running. Port sessions require an advertised port-stream-capable agent and a TCP guest port that is already published by the sandbox. Pending and connected sessions are limited to 20 per tenant, 10 per agent, and 5 per sandbox; a limit breach returns 429.

- Use isolated fixtures and clean up recorded resource identifiers.

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
  "columns": 80,
  "kind": "pty",
  "rows": 24
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
  "${POSTGRIP_API_URL}/api/v1/sandboxes/${POSTGRIP_SANDBOX_ID}/sessions" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/sandboxes/" + url.PathEscape(os.Getenv("POSTGRIP_SANDBOX_ID")) + "/sessions")
if err != nil { return err }
body := strings.NewReader("{\"columns\":80,\"kind\":\"pty\",\"rows\":24}")
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
const url = new URL(baseUrl + "/api/v1/sandboxes/" + encodeURIComponent(process.env.POSTGRIP_SANDBOX_ID ?? "") + "/sessions");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"columns\":80,\"kind\":\"pty\",\"rows\":24}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/sandboxes/' + urllib.parse.quote(os.environ['POSTGRIP_SANDBOX_ID'], safe='') + '/sessions'
request = urllib.request.Request(endpoint, data='{"columns":80,"kind":"pty","rows":24}'.encode(), method='POST')
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
- [deleteSandbox](./deleteSandbox.md) — Request sandbox deletion
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes
- [listWorkspaces](./listWorkspaces.md) — List uploaded workspaces

[Back to Agent index](./README.md)
