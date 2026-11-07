# List service webhook dispatch events

`GET /api/v1/services/project/{serviceId}/webhook-events` · `listServiceWebhookDispatchEvents` · Service

> Contract bundle `542f7668e1b52416728881094d1186fce807db26bd99afa3af6f5c9260c99cdf`
> Service contract `37484d91ca60df1f18de9d8d4b1f8b8931e108212372a2c829e673fd83c9191b`

Lists the bounded recent decisions produced while dispatching GitHub push and pull-request events for a service. Only an app (a project service) has these; a connected service's id answers `404` `SERVICE_NOT_FOUND`.

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
| `limit` | query | no | `integer` | `1` | Page size, from 1 to 100; any other value is refused with `400` `VALIDATION`. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `array<ServiceWebhookDispatchEvent>` |
| `400` | Invalid request. `VALIDATION`: `limit` is not a whole number from 1 to 100. | `application/json` | `ErrorResponse` |
| `404` | Not found. `SERVICE_NOT_FOUND`: the id is not a UUID, or names no app of the tenant. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
    "action": "string",
    "branch": "string",
    "commitSha": "string",
    "createdAt": "2026-01-01T00:00:00Z",
    "decision": "string",
    "deploymentId": "11111111-1111-4111-8111-111111111111",
    "environmentId": "11111111-1111-4111-8111-111111111111",
    "eventType": "string",
    "id": "11111111-1111-4111-8111-111111111111",
    "prNumber": 1,
    "projectId": "11111111-1111-4111-8111-111111111111",
    "reason": "string",
    "tenantId": "11111111-1111-4111-8111-111111111111"
  }
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns the bounded recent decisions made while handling GitHub push and pull-request webhook events for one service.

- Use event state and safe reason fields for diagnosis; this history does not contain webhook secrets.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/webhook-events" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/webhook-events")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/webhook-events");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/webhook-events'
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
- [getServiceDeploymentScreenshot](./getServiceDeploymentScreenshot.md) — Download Deployment Screenshot
- [listServiceDeployments](./listServiceDeployments.md) — List service deployments

[Back to Service index](./README.md)
