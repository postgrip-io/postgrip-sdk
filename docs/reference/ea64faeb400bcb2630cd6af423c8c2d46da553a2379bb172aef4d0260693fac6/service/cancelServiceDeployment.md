# Cancel a queued service deployment

`POST /api/v1/services/project/{serviceId}/deployments/{deploymentId}/cancel` · `cancelServiceDeployment` · Service

> Contract bundle `ea64faeb400bcb2630cd6af423c8c2d46da553a2379bb172aef4d0260693fac6`
> Service contract `a24582ed09d34f162aaf200848201038e934613fd0254e1cdb9fa258275a6c22`

Uses the contract-defined POST /api/v1/services/project/{serviceId}/deployments/{deploymentId}/cancel behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Operations` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:operate"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `deploymentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Deployment cancelled | `application/json` | `DeploymentOperationResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "deployment": {
    "aliases": [
      "https://www.example.com/"
    ],
    "branch": "string",
    "commitSha": "string",
    "createdAt": "2026-01-01T00:00:00Z",
    "cutoverState": "candidate",
    "environmentId": "11111111-1111-4111-8111-111111111111",
    "id": "11111111-1111-4111-8111-111111111111",
    "isCurrent": true,
    "projectId": "11111111-1111-4111-8111-111111111111",
    "status": "string",
    "triggerKind": "string",
    "updatedAt": "2026-01-01T00:00:00Z"
  },
  "deploymentId": "11111111-1111-4111-8111-111111111111",
  "environmentId": "11111111-1111-4111-8111-111111111111",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "serviceRef": "string",
  "status": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined POST /api/v1/services/project/{serviceId}/deployments/{deploymentId}/cancel behavior.

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
: "${POSTGRIP_DEPLOYMENT_ID:?set POSTGRIP_DEPLOYMENT_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/deployments/${POSTGRIP_DEPLOYMENT_ID}/cancel" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/deployments/" + url.PathEscape(os.Getenv("POSTGRIP_DEPLOYMENT_ID")) + "/cancel")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))

request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/deployments/" + encodeURIComponent(process.env.POSTGRIP_DEPLOYMENT_ID ?? "") + "/cancel");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/deployments/' + urllib.parse.quote(os.environ['POSTGRIP_DEPLOYMENT_ID'], safe='') + '/cancel'
request = urllib.request.Request(endpoint, method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")

request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [checkService](./checkService.md) — Probe a target or deployed service
- [deployService](./deployService.md) — Queue a deployment for a confirmed commit
- [previewServiceDeploy](./previewServiceDeploy.md) — Resolve a deploy request to an immutable commit
- [redeployService](./redeployService.md) — Queue a deployment from an existing immutable revision
- [restartServiceRuntime](./restartServiceRuntime.md) — Restart the exact current service runtime
- [rollbackServiceDeployment](./rollbackServiceDeployment.md) — Queue rollback to a historical service deployment
- [startServiceRuntime](./startServiceRuntime.md) — Start the exact current service runtime
- [stopServiceRuntime](./stopServiceRuntime.md) — Stop the exact current service runtime

[Back to Service index](./README.md)
