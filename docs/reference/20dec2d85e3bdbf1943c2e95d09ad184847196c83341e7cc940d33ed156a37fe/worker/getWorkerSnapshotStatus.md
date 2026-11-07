# Read a worker's snapshot status

`GET /api/v1/workers/{workerId}/snapshot/status` · `getWorkerSnapshotStatus` · Worker

> Contract bundle `20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`
> Worker contract `86004c9dd3c7b8cf629e47141a53e4fcfb97f633294b96a68bec1c67f957fcce`

The Worker's snapshot schedule and its last run, as PostGrip projects them. Answered when snapshots are off, with `enabled: false`. `degraded` is true when the last snapshot succeeded without capturing everything; `lastSkipped` says what, by kind. `lastExcluded` lists what it left out by the settings' choice, such as the volumes of worker-managed databases with `volumesEnabled` off; that does not make it degraded. `lastRunFailed` and `settingsRejected` report that the last run failed and that saved settings are not in effect; the Worker's error text is not answered. `recovery` is the Worker's restore report when it was recovered from another Worker's archive. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. A pending or revoked Worker, or one the fence finds replaced, revoked or removed, answers `409` `WORKER_NOT_LIVE` with `details.status`. A Worker that doesn't advertise the `worker_snapshot_api_v1` capability answers `409` `WORKER_UPGRADE_REQUIRED` with `details.requiredCapability`; upgrade it and retry. Nothing is sent to the Worker for these. A Worker that doesn't answer is `502` `WORKER_UNAVAILABLE`, any answer outside the operation's own is `502` `WORKER_REFUSED`, and a malformed or oversized one is `502` `INVALID_WORKER_RESPONSE`. The Worker's own messages are never answered.

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
| `200` | Snapshot status | `application/json` | `WorkerSnapshotStatus` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "cron": "0 3 * * *",
  "degraded": false,
  "enabled": true,
  "lastExcluded": [],
  "lastRunAt": "2026-11-07T03:00:00Z",
  "lastRunFailed": false,
  "lastSkipped": [],
  "lastSnapshot": {
    "lastModified": "2026-11-07T03:00:41Z",
    "objectKey": "worker-snapshots/9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11/20261107T030000.000Z.pgsnap",
    "size": 1048576,
    "snapshotId": "20261107T030000.000Z"
  },
  "lastSuccessAt": "2026-11-07T03:00:41Z",
  "nextRunAt": "2026-11-08T03:00:00Z",
  "retention": 7,
  "running": false,
  "settingsRejected": false,
  "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Reads the Worker's snapshot schedule and last run as PostGrip projects them, answered with `enabled: false` when snapshots are off. `degraded` and `lastSkipped` report an incomplete last snapshot; `lastRunFailed` and `settingsRejected` report a failed run and settings not in effect without the Worker's error text. Requires the `worker_snapshot_api_v1` capability.

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
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}/snapshot/status" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")) + "/snapshot/status")
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
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/snapshot/status");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/snapshot/status'
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
- [listStorageDestinations](./listStorageDestinations.md) — List storage destinations
- [listWorkerSnapshots](./listWorkerSnapshots.md) — List a worker's snapshots
- [updateWorkerSnapshotSettings](./updateWorkerSnapshotSettings.md) — Replace a worker's snapshot settings

[Back to Worker index](./README.md)
