# Trim Service Runtime Logs

`POST /api/v1/services/project/{serviceId}/logs/runtime/trim` · `trimServiceRuntimeLogs` · Service

> Contract bundle `449013ff4353f04b4575140417b29c823749ece0747ffaea04bceb79464a59f8`
> Service contract `579b9db5db30698a034365b17d5accc8af481517a99a9a9add4702ae08af13a1`

Uses the contract-defined POST /api/v1/services/project/{serviceId}/logs/runtime/trim behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:admin"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environmentId` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Successful response | `application/json` | `ServiceRuntimeLogMutationResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "configurationOperationId": "11111111-1111-4111-8111-111111111111",
  "effect": "string",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "settings": {
    "consistency": "uniform",
    "etag": "string",
    "items": [
      {
        "available": true,
        "environmentId": "11111111-1111-4111-8111-111111111111",
        "version": 1,
        "workerId": "11111111-1111-4111-8111-111111111111"
      }
    ],
    "version": 1
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined POST /api/v1/services/project/{serviceId}/logs/runtime/trim behavior.

- Idempotency: required.
- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  POST \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/logs/runtime/trim" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/logs/runtime/trim")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))

request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
request.Header.Set("If-Match", os.Getenv("POSTGRIP_IF_MATCH"))
client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/logs/runtime/trim");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/logs/runtime/trim'
request = urllib.request.Request(endpoint, method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")

request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
request.add_header('If-Match', os.environ["POSTGRIP_IF_MATCH"])
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
