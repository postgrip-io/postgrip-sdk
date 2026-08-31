# Get a deployment browser-check screenshot

`GET /api/v1/services/project/{serviceId}/deployments/{deploymentId}/screenshot` · `getServiceDeploymentScreenshot` · Service

> Contract bundle `e87cf4a389d51e12f842ecf22ad3bb5d68ec0ec4798febf79b1e256fa80945bb`
> Service contract `6025a5fd77c3754d17c553dc72509452741748555b4137950ad5a47153b8f717`

Downloads the browser-check screenshot captured by the Worker for an exact tenant-owned deployment.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Deployments` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `deploymentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Deployment screenshot | `application/json` | `ServiceDeploymentScreenshot` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "contentType": "string",
  "dataBase64": "cG9zdGdyaXA="
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns a bounded base64-encoded browser-check screenshot for an exact tenant-owned deployment after resolving its assigned Worker through the service catalog.

- Decode into a protected local file and do not treat image availability as proof of current public reachability.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_DEPLOYMENT_ID:?set POSTGRIP_DEPLOYMENT_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/deployments/${POSTGRIP_DEPLOYMENT_ID}/screenshot" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/deployments/" + url.PathEscape(os.Getenv("POSTGRIP_DEPLOYMENT_ID")) + "/screenshot")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/deployments/" + encodeURIComponent(process.env.POSTGRIP_DEPLOYMENT_ID ?? "") + "/screenshot");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/deployments/' + urllib.parse.quote(os.environ['POSTGRIP_DEPLOYMENT_ID'], safe='') + '/screenshot'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [getServiceDeployment](./getServiceDeployment.md) — Get a service deployment
- [listServiceDeployments](./listServiceDeployments.md) — List service deployments
- [listServiceWebhookDispatchEvents](./listServiceWebhookDispatchEvents.md) — List Webhook Dispatch Events

[Back to Service index](./README.md)
