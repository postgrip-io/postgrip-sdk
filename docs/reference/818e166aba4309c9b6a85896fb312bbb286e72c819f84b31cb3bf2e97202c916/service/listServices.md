# List services

`GET /api/v1/services` · `listServices` · Service

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Service contract `95872979a1e84bd2915f33ce6c2326aec2e0cf77ba2e474f65e08d619efbe439`

Uses the contract-defined GET /api/v1/services behavior.

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
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `kind` | query | no | `ServiceKind` | `"postgresql"` | — |
| `mode` | query | no | `ServiceMode` | `"connected"` | — |
| `status` | query | no | `ServiceStatusValue` | `"ready"` | — |
| `worker` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `limit` | query | no | `integer` | `1` | Page size. A missing, non-numeric, zero or negative value means 100, and a value above 200 means 200; neither is refused. |
| `cursor` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Services | `application/json` | `ServiceList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "catalogEtag": "string",
  "catalogVersion": 1,
  "items": [
    {
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
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services")
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
const url = new URL(baseUrl + "/api/v1/services");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services'
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
- [getServiceStatus](./getServiceStatus.md) — Get last-known service and environment status
- [resolveService](./resolveService.md) — Resolve an exact service reference, ID, or name

[Back to Service index](./README.md)
