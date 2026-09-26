# Get last-known service and environment status

`GET /api/v1/services/{source}/{serviceId}/status` · `getServiceStatus` · Service

> Contract bundle `aa3e67f82feac02dccb628c161e05394052a9041618fafcd1942c9afa034897e`
> Service contract `fcc4e361e8c0b864105c18233fa519e0ea9fa8ccebf91eb838a49b297be6ca27`

Uses the contract-defined GET /api/v1/services/{source}/{serviceId}/status behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Services` |
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
| `source` | path | yes | `ServiceSource` | `"target"` | — |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environment` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Service status | `application/json` | `ServiceStatus` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "environments": [
    {
      "aliases": [
        "https://www.example.com/"
      ],
      "createdAt": "2026-01-01T00:00:00Z",
      "id": "11111111-1111-4111-8111-111111111111",
      "kind": "postgresql",
      "name": "string",
      "projectId": "11111111-1111-4111-8111-111111111111",
      "status": "ready",
      "updatedAt": "2026-01-01T00:00:00Z"
    }
  ],
  "service": {
    "capabilities": [
      "check"
    ],
    "configurationEtag": "string",
    "configurationVersion": 1,
    "createdAt": "2026-01-01T00:00:00Z",
    "environmentCount": 1,
    "facets": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "source": "target"
      }
    ],
    "id": "11111111-1111-4111-8111-111111111111",
    "kind": "postgresql",
    "mode": "connected",
    "name": "string",
    "ref": "project:11111111-1111-4111-8111-111111111111",
    "slug": "string",
    "source": "target",
    "status": "ready",
    "updatedAt": "2026-01-01T00:00:00Z",
    "workers": [
      {
        "id": "11111111-1111-4111-8111-111111111111",
        "name": "string"
      }
    ]
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services/{source}/{serviceId}/status behavior.

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
  "${POSTGRIP_API_URL}/api/v1/services/${POSTGRIP_SOURCE}/${POSTGRIP_SERVICE_ID}/status" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/" + url.PathEscape(os.Getenv("POSTGRIP_SOURCE")) + "/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/status")
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
const url = new URL(baseUrl + "/api/v1/services/" + encodeURIComponent(process.env.POSTGRIP_SOURCE ?? "") + "/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/status");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/' + urllib.parse.quote(os.environ['POSTGRIP_SOURCE'], safe='') + '/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/status'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [getService](./getService.md) — Get a service and its capabilities
- [listServices](./listServices.md) — List services
- [resolveService](./resolveService.md) — Resolve an exact service reference, ID, or name

[Back to Service index](./README.md)
