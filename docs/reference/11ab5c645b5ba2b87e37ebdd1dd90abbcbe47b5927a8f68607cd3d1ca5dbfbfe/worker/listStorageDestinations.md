# List storage destinations

`GET /api/v1/storage-destinations` · `listStorageDestinations` · Worker

> Contract bundle `11ab5c645b5ba2b87e37ebdd1dd90abbcbe47b5927a8f68607cd3d1ca5dbfbfe`
> Worker contract `86004c9dd3c7b8cf629e47141a53e4fcfb97f633294b96a68bec1c67f957fcce`

The organization's storage destinations, ordered by name: the buckets a Worker's snapshots can go to. Use a destination's `id` as `storageDestinationId` in `updateWorkerSnapshotSettings`. Not paged. The answer holds no credential: a destination's access key and secret stay on the Workers that use it, and which Workers hold them is not answered. Adding a destination and delivering its credentials is done on the console's Storage page.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Snapshots` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["workers:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Storage destinations | `application/json` | `StorageDestinationList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "accountId": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
      "bucket": "pg-backups",
      "createdAt": "2026-11-01T09:30:00Z",
      "endpoint": "https://1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d.r2.cloudflarestorage.com",
      "id": "0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a",
      "name": "Production backups",
      "prefix": "postgrip",
      "provider": "r2",
      "updatedAt": "2026-11-01T09:30:00Z"
    },
    {
      "bucket": "acme-worker-snapshots",
      "createdAt": "2026-10-20T14:05:12Z",
      "id": "7e3f9a1b-2c4d-4e5f-8a6b-9c0d1e2f3a4b",
      "name": "us-east archive",
      "provider": "s3",
      "region": "us-east-1",
      "updatedAt": "2026-11-03T08:00:00Z"
    }
  ]
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Lists the organization's storage destinations, ordered by name and not paged; a destination's `id` is the `storageDestinationId` that `updateWorkerSnapshotSettings` takes. The answer holds no credential: the access key and secret stay on the Workers that use the destination, and which Workers hold them is not answered. No Worker is contacted.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
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
  "${POSTGRIP_API_URL}/api/v1/storage-destinations" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/storage-destinations")
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
const url = new URL(baseUrl + "/api/v1/storage-destinations");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/storage-destinations'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [createWorkerSnapshot](./createWorkerSnapshot.md) — Take a worker snapshot now
- [getWorkerSnapshotSettings](./getWorkerSnapshotSettings.md) — Read a worker's snapshot settings
- [getWorkerSnapshotStatus](./getWorkerSnapshotStatus.md) — Read a worker's snapshot status
- [listWorkerSnapshots](./listWorkerSnapshots.md) — List a worker's snapshots
- [updateWorkerSnapshotSettings](./updateWorkerSnapshotSettings.md) — Replace a worker's snapshot settings

[Back to Worker index](./README.md)
