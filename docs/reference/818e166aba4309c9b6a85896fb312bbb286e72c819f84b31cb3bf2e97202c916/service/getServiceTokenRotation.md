# Get a service token rotation

`GET /api/v1/services/project/{serviceId}/token/rotations/{rotationId}` · `getServiceTokenRotation` · Service

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Service contract `95872979a1e84bd2915f33ce6c2326aec2e0cf77ba2e474f65e08d619efbe439`

Reads a rotation that rotateServiceToken started, and how its redeploy went. It never answers the token.

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
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `rotationId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceTokenRotation` |
| `404` | Not found. `SERVICE_NOT_FOUND`: `serviceId` or `rotationId` is not a UUID, or names no rotation of the tenant's service. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "attemptCount": 1,
  "completedAt": "2026-01-01T00:00:00Z",
  "configurationOperationId": "11111111-1111-4111-8111-111111111111",
  "configurationOperationState": "string",
  "createdAt": "2026-01-01T00:00:00Z",
  "deploymentId": "11111111-1111-4111-8111-111111111111",
  "environmentId": "11111111-1111-4111-8111-111111111111",
  "errorCode": "string",
  "expectedLatestDeploymentId": "11111111-1111-4111-8111-111111111111",
  "id": "11111111-1111-4111-8111-111111111111",
  "serviceId": "11111111-1111-4111-8111-111111111111",
  "state": "configuring",
  "updatedAt": "2026-01-01T00:00:00Z",
  "variableId": "11111111-1111-4111-8111-111111111111"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Reads a rotation that rotateServiceToken started: its configuration operation and that operation's state, the rotation's state (configuring, redeploying, redeployed, deployed_since, not_needed, replaced, redeploy_failed or stopped), the redeploy's fenced and resulting deployments, and errorCode. It never answers the token.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_ROTATION_ID:?set POSTGRIP_ROTATION_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/token/rotations/${POSTGRIP_ROTATION_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/token/rotations/" + url.PathEscape(os.Getenv("POSTGRIP_ROTATION_ID")))
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/token/rotations/" + encodeURIComponent(process.env.POSTGRIP_ROTATION_ID ?? ""));

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/token/rotations/' + urllib.parse.quote(os.environ['POSTGRIP_ROTATION_ID'], safe='')
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [abandonServiceConfigurationOperation](./abandonServiceConfigurationOperation.md) — Abandon Service Configuration Operation
- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value

[Back to Service index](./README.md)
