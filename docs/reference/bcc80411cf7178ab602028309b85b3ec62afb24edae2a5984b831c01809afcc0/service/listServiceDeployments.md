# List service deployments

`GET /api/v1/services/{source}/{serviceId}/deployments` · `listServiceDeployments` · Service

> Contract bundle `bcc80411cf7178ab602028309b85b3ec62afb24edae2a5984b831c01809afcc0`
> Service contract `5e00de2583b47ec1ca6632b84307ff0529e13ad2f50d481ea2504de98fe5c12e`

Lists a project service's deployments, newest first. A connected service (`source` `target`) has none: `409` `SERVICE_OPERATION_NOT_SUPPORTED`.

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
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `source` | path | yes | `ServiceSource` | `"target"` | — |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `status` | query | no | `string` | `"queued"` | Only deployments with this status, in any letter case. Any other value is refused with `400` `INVALID_FILTER`. |
| `limit` | query | no | `integer` | `1` | Page size. A missing, non-numeric, zero or negative value means 100, and a value above 200 means 200; neither is refused. |
| `cursor` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Deployments | `application/json` | `DeploymentList` |
| `400` | Invalid request. `INVALID_FILTER`: `status` is not a deployment status, or `environment` is not an environment id (`message` says which). `INVALID_CURSOR`: the cursor is not one PostGrip issued for this request. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
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
      "status": "queued",
      "triggerKind": "string",
      "updatedAt": "2026-01-01T00:00:00Z"
    }
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services/{source}/{serviceId}/deployments behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SOURCE:?set POSTGRIP_SOURCE to a percent-encoded path value}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/${POSTGRIP_SOURCE}/${POSTGRIP_SERVICE_ID}/deployments" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/" + url.PathEscape(os.Getenv("POSTGRIP_SOURCE")) + "/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/deployments")
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
const url = new URL(baseUrl + "/api/v1/services/" + encodeURIComponent(process.env.POSTGRIP_SOURCE ?? "") + "/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/deployments");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/' + urllib.parse.quote(os.environ['POSTGRIP_SOURCE'], safe='') + '/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/deployments'
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
- [listServiceWebhookDispatchEvents](./listServiceWebhookDispatchEvents.md) — List Webhook Dispatch Events

[Back to Service index](./README.md)
