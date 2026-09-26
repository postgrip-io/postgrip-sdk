# Get a service traffic report

`GET /api/v1/services/project/{serviceId}/traffic/report` · `getServiceTrafficReport` · Service

> Contract bundle `aa3e67f82feac02dccb628c161e05394052a9041618fafcd1942c9afa034897e`
> Service contract `fcc4e361e8c0b864105c18233fa519e0ea9fa8ccebf91eb838a49b297be6ca27`

Returns bounded traffic time-series and breakdown data from every assigned Worker.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Observability` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:logs:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | Resolved environment UUID. When omitted, the operation covers every assigned environment in the project. |
| `window` | query | no | `string` | `"1h"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceTrafficReportFanout` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "complete": true,
  "items": [
    {
      "data": {
        "bucketUnit": "string",
        "byEnvironmentId": [
          {
            "bytes": 1,
            "key": "string",
            "requests": 1
          }
        ],
        "summary": {
          "avgLatencyMs": 1.0,
          "bytes": 1,
          "hosts": 1,
          "requests": 1,
          "status2xx": 1,
          "status3xx": 1,
          "status4xx": 1,
          "status5xx": 1
        },
        "timeSeries": [
          {
            "avgLatencyMs": 1.0,
            "bucketStart": "2026-01-01T00:00:00Z",
            "bytes": 1,
            "requests": 1
          }
        ],
        "topHosts": [
          {
            "bytes": 1,
            "key": "string",
            "requests": 1
          }
        ],
        "topPaths": [
          {
            "bytes": 1,
            "key": "string",
            "requests": 1
          }
        ],
        "window": "1h"
      },
      "environmentIds": [
        "11111111-1111-4111-8111-111111111111"
      ],
      "workerId": "11111111-1111-4111-8111-111111111111"
    }
  ]
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns bounded time-series and path, host, and environment breakdowns from every Worker assigned to the project or selected environment.

- A false complete field preserves successful Worker data but indicates a partial failure.

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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/traffic/report" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/traffic/report")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/traffic/report");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/traffic/report'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [flushServiceTraffic](./flushServiceTraffic.md) — Flush Service Traffic Telemetry
- [getServiceTrafficStatus](./getServiceTrafficStatus.md) — Get Service Traffic Status
- [putServiceTrafficSettings](./putServiceTrafficSettings.md) — Update Service Traffic Settings
- [trimServiceTraffic](./trimServiceTraffic.md) — Trim Service Traffic Telemetry

[Back to Service index](./README.md)
