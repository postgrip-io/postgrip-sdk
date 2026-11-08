# Trim service traffic telemetry

`POST /api/v1/services/project/{serviceId}/traffic/trim` · `trimServiceTraffic` · Service

> Contract bundle `9b1659218aa56bbbf542bf55d9475c7cf16ae036b531c72c099adc738203d439`
> Service contract `5120be17f89162a536c3c0bf8f9cf859862a0187d5c8616d393b4d3fdca7cf12`

Deletes traffic rollups older than the configured retention window on every selected Worker. Only an app (a project service) has these; a connected service's id answers `404` `SERVICE_NOT_FOUND`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Observability` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:admin"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environment` | query | no | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | Resolved environment UUID. When omitted, the operation covers every assigned environment in the project. |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Per-Worker results | `application/json` | `ServiceTrafficMaintenanceFanout` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "complete": true,
  "items": [
    {
      "data": {
        "compacted": true,
        "completedAt": "2026-01-01T00:00:00Z",
        "deletedRows": 1,
        "operation": "trim",
        "settings": {
          "enabled": true,
          "retentionDays": 1,
          "tenantId": "11111111-1111-4111-8111-111111111111",
          "updatedAt": "2026-01-01T00:00:00Z"
        },
        "storage": {
          "databaseBytes": 1,
          "distinctHosts": 1,
          "rollupRows": 1,
          "totalRequests": 1
        }
      },
      "environmentIds": [
        "11111111-1111-4111-8111-111111111111"
      ],
      "workerId": "11111111-1111-4111-8111-111111111111"
    }
  ],
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

Deletes traffic telemetry rollups older than the configured retention window on every selected Worker and returns a result for each Worker.

- Idempotency: required.
- A false complete field is a partial failure and must not be treated as success.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/traffic/trim" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/traffic/trim")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/traffic/trim");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/traffic/trim'
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

- [flushServiceTraffic](./flushServiceTraffic.md) — Flush Service Traffic Telemetry
- [getServiceTrafficReport](./getServiceTrafficReport.md) — Get Service Traffic Report
- [getServiceTrafficStatus](./getServiceTrafficStatus.md) — Get Service Traffic Status
- [putServiceTrafficSettings](./putServiceTrafficSettings.md) — Update Service Traffic Settings

[Back to Service index](./README.md)
