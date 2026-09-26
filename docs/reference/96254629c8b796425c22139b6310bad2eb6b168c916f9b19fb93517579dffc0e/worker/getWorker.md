# Get a worker

`GET /api/v1/workers/{workerId}` · `getWorker` · Worker

> Contract bundle `96254629c8b796425c22139b6310bad2eb6b168c916f9b19fb93517579dffc0e`
> Worker contract `ffce1b8c3053f64e6efa1740a9ae8c124cbc6f49fc0754d51e608688ed115dc7`

Uses the contract-defined GET /api/v1/workers/{workerId} behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Workers` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["workers:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workerId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Worker | `application/json` | `Worker` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "autoShutdownOnRemoval": true,
  "capabilities": [
    "string"
  ],
  "createdAt": "2026-01-01T00:00:00Z",
  "id": "11111111-1111-4111-8111-111111111111",
  "name": "string",
  "previewSubdomainEnabled": true,
  "status": "string",
  "trustState": "string",
  "updatedAt": "2026-01-01T00:00:00Z"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/workers/{workerId} behavior.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKER_ID:?set POSTGRIP_WORKER_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")))
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
const baseUrl = process.env.POSTGRIP_WORKER_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? ""));

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='')
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [checkWorker](./checkWorker.md) — Check worker connectivity and trust
- [createWorker](./createWorker.md) — Create a pending Worker with client-owned bootstrap material
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance
- [upgradeWorker](./upgradeWorker.md) — Queue a bounded worker-host upgrade

[Back to Worker index](./README.md)
