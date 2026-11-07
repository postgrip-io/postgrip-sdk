# List a worker's snapshots

`GET /api/v1/workers/{workerId}/snapshots` · `listWorkerSnapshots` · Worker

> Contract bundle `f9a7580a7b8fdde0c75e222d8301b94338bc291d6e942a29da29352a482adc8f`
> Worker contract `538a02d973231fb350dd5f87cd0ef62731a7a99456be534d076b40a5009cc1d9`

The Worker's archives in its storage destination, newest first; at most what its retention keeps. Not paged. Snapshots that are off answer `409` `SNAPSHOTS_DISABLED`, and a listing the Worker could not read `502` `SNAPSHOT_LIST_FAILED`. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. A pending or revoked Worker, or one the fence finds replaced, revoked or removed, answers `409` `WORKER_NOT_LIVE` with `details.status`. A Worker that doesn't advertise the `worker_snapshot_api_v1` capability answers `409` `WORKER_UPGRADE_REQUIRED` with `details.requiredCapability`; upgrade it and retry. Nothing is sent to the Worker for these. A Worker that doesn't answer is `502` `WORKER_UNAVAILABLE`, any answer outside the operation's own is `502` `WORKER_REFUSED`, and a malformed or oversized one is `502` `INVALID_WORKER_RESPONSE`. The Worker's own messages are never answered.

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

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workerId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Snapshots | `application/json` | `WorkerSnapshotList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "lastModified": "2026-11-07T03:00:41Z",
      "objectKey": "worker-snapshots/9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11/20261107T030000.000Z.pgsnap",
      "size": 1048576,
      "snapshotId": "20261107T030000.000Z"
    }
  ]
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Lists the Worker's archives in its storage destination, newest first and not paged. Snapshots that are off answer `409` `SNAPSHOTS_DISABLED`. Requires the `worker_snapshot_api_v1` capability.

- Requires snapshots enabled on a Worker whose storage destination credentials were delivered from the console.

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
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}/snapshots" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")) + "/snapshots")
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
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/snapshots");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/snapshots'
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
- [updateWorkerSnapshotSettings](./updateWorkerSnapshotSettings.md) — Replace a worker's snapshot settings

[Back to Worker index](./README.md)
