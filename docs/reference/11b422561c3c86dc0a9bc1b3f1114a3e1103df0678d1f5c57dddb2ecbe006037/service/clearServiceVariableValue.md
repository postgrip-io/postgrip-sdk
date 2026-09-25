# Clear Service Variable Value

`DELETE /api/v1/services/project/{serviceId}/environments/{environmentId}/variables/{variableId}/value` · `clearServiceVariableValue` · Service

> Contract bundle `11b422561c3c86dc0a9bc1b3f1114a3e1103df0678d1f5c57dddb2ecbe006037`
> Service contract `99343f05168d91c78b62d4de355a9e72611cb9be7a1a7691873c8cf469d2e1aa`

Uses the contract-defined DELETE /api/v1/services/project/{serviceId}/environments/{environmentId}/variables/{variableId}/value behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:write","services:secrets:write"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environmentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `variableId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Successful response | `application/json` | `ServiceVariableMutationResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "collectionVersion": 1,
  "configurationOperationId": "11111111-1111-4111-8111-111111111111",
  "configurationRevision": 1,
  "effect": "string",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined DELETE /api/v1/services/project/{serviceId}/environments/{environmentId}/variables/{variableId}/value behavior.

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
: "${POSTGRIP_ENVIRONMENT_ID:?set POSTGRIP_ENVIRONMENT_ID to a percent-encoded path value}"
: "${POSTGRIP_VARIABLE_ID:?set POSTGRIP_VARIABLE_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  DELETE \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/variables/${POSTGRIP_VARIABLE_ID}/value" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/variables/" + url.PathEscape(os.Getenv("POSTGRIP_VARIABLE_ID")) + "/value")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "DELETE", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/variables/" + encodeURIComponent(process.env.POSTGRIP_VARIABLE_ID ?? "") + "/value");

const response = await fetch(url, {
  method: "DELETE",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/variables/' + urllib.parse.quote(os.environ['POSTGRIP_VARIABLE_ID'], safe='') + '/value'
request = urllib.request.Request(endpoint, method='DELETE')
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
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection
- [createPostGripConfigurationPlan](./createPostGripConfigurationPlan.md) — Create PostGrip Configuration Plan

[Back to Service index](./README.md)
