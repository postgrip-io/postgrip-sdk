# List declarative configuration operation actions

`GET /api/v1/services/configuration-stacks/{stackKey}/operations/{operationId}/actions` · `listPostGripConfigurationStackOperationActions` · Service

> Contract bundle `875bb2efc163f5df9b0b9f91a95edae9206db3cac5efa90b88565a7f3ff14bcf`
> Service contract `255550d7cb8a8c6662ad1b7944412d9cca4e5d1c0f181a002770e776c1d9b158`

Returns one bounded, cursor-paginated page of durable aggregate action receipts. Secret actions expose opaque input identifiers and versions, never submitted values or sealed envelopes.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `stackKey` | path | yes | `string` | `"recorded"` | — |
| `operationId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `limit` | query | no | `integer` | `1` | — |
| `cursor` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `PostGripConfigurationStackOperationActionList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "attemptCount": 1,
      "dependencies": [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ],
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "kind": "create",
      "path": "string",
      "resourceType": "project",
      "retryable": true,
      "state": "pending",
      "updatedAt": "2026-01-01T00:00:00Z"
    }
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns one bounded, cursor-paginated page of durable aggregate action receipts. Secret actions expose opaque input identifiers and versions, never submitted values or sealed envelopes.

- Follow nextCursor until it is empty to consume the complete operation history.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_STACK_KEY:?set POSTGRIP_STACK_KEY to a percent-encoded path value}"
: "${POSTGRIP_OPERATION_ID:?set POSTGRIP_OPERATION_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/configuration-stacks/${POSTGRIP_STACK_KEY}/operations/${POSTGRIP_OPERATION_ID}/actions" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration-stacks/" + url.PathEscape(os.Getenv("POSTGRIP_STACK_KEY")) + "/operations/" + url.PathEscape(os.Getenv("POSTGRIP_OPERATION_ID")) + "/actions")
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
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/configuration-stacks/" + encodeURIComponent(process.env.POSTGRIP_STACK_KEY ?? "") + "/operations/" + encodeURIComponent(process.env.POSTGRIP_OPERATION_ID ?? "") + "/actions");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration-stacks/' + urllib.parse.quote(os.environ['POSTGRIP_STACK_KEY'], safe='') + '/operations/' + urllib.parse.quote(os.environ['POSTGRIP_OPERATION_ID'], safe='') + '/actions'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection

[Back to Service index](./README.md)
