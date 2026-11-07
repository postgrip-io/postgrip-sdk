# Preview a worker's removal

`GET /api/v1/workers/{workerId}/removal-impact` · `getWorkerRemovalImpact` · Worker

> Contract bundle `a20586b1bf0a44746bca6b9d4fd8511a50be823ca55450324efd077ebaca00f5`
> Worker contract `40a51d3084dc368881b163637b025f45bb412f6d3525d3caf2842dbda1706460`

What removing the Worker would delete or change, the read `removeWorker` confirms. `serviceCount` services (targets) on the Worker are deleted with it. Each of `projects` has an environment on the Worker or the Worker as its default: an `exclusive` project, whose every environment assigned a Worker is on this one, is deleted; any other is kept, its environments on the Worker are unassigned, and a `usesAsDefault` project's default Worker is cleared. A Worker with `managedVolumeCount` above zero cannot be removed until its managed volumes are deleted or moved; `unreachableVolumes` are those of a lost Worker, still counted, which only the console's Remove Worker dialog can abandon. The `ETag` header, equal to the body's `etag`, is the impact's fence: send it as `If-Match` with `removeWorker`. It changes when what the removal would do changes, including when a Worker becomes lost; it does not change when a project is renamed, and it does not expire. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. Read-only and not audited.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Workers` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["workers:admin"]]` |
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
| `200` | Worker removal impact | `application/json` | `WorkerRemovalImpact` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "etag": "\"worker-removal-5f2c0e9a7b1d4c3e8a6f0b2d9c4e7a1f\"",
  "managedVolumeCount": 0,
  "projects": [
    {
      "exclusive": true,
      "id": "3c8e2a1f-5b7d-4e9c-a2f0-6d1b8e4c7a93",
      "name": "storefront",
      "usesAsDefault": false
    },
    {
      "exclusive": false,
      "id": "7a4d9e2c-1f3b-4c8a-b6e0-2d5f9a1c3e78",
      "name": "billing",
      "usesAsDefault": true
    }
  ],
  "serviceCount": 2,
  "unreachableVolumes": [],
  "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/workers/{workerId}/removal-impact behavior.

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
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}/removal-impact" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")) + "/removal-impact")
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
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/removal-impact");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/removal-impact'
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
- [getWorker](./getWorker.md) — Get a worker
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [removeWorker](./removeWorker.md) — Remove a worker
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance

[Back to Worker index](./README.md)
