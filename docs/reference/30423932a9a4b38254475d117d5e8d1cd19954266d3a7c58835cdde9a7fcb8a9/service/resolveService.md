# Resolve an exact service reference, ID, or name

`GET /api/v1/services/resolve` · `resolveService` · Service

> Contract bundle `30423932a9a4b38254475d117d5e8d1cd19954266d3a7c58835cdde9a7fcb8a9`
> Service contract `06d879f256e9a90899abac6d615cd1619d212d1db2f3e6778c26473da38ca45f`

Uses the contract-defined GET /api/v1/services/resolve behavior.

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
| `value` | query | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Resolved service | `application/json` | `Service` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
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
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/services/resolve behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_VALUE:?set POSTGRIP_VALUE to a percent-encoded query value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/resolve?value=${POSTGRIP_VALUE}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/resolve")
if err != nil { return err }
query := endpoint.Query()
query.Set("value", os.Getenv("POSTGRIP_VALUE"))
endpoint.RawQuery = query.Encode()
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
const url = new URL(baseUrl + "/api/v1/services/resolve");
url.searchParams.set('value', process.env.POSTGRIP_VALUE ?? "");
const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/resolve'
query = urllib.parse.urlencode({'value': os.environ["POSTGRIP_VALUE"]})
endpoint += '?' + query
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
- [listServices](./listServices.md) — List services

[Back to Service index](./README.md)
