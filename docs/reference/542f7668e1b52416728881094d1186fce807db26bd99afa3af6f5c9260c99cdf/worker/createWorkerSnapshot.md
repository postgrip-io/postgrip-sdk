# Take a worker snapshot now

`POST /api/v1/workers/{workerId}/snapshots` · `createWorkerSnapshot` · Worker

> Contract bundle `542f7668e1b52416728881094d1186fce807db26bd99afa3af6f5c9260c99cdf`
> Worker contract `538a02d973231fb350dd5f87cd0ef62731a7a99456be534d076b40a5009cc1d9`

Runs a snapshot on the Worker and waits for it, at most 5 minutes; the Worker keeps running one that takes longer. `snapshot.degraded` and `snapshot.skipped` report anything the archive could not capture. `snapshot.excluded` reports what it left out by the settings' choice, which is not degraded. Snapshots that are off answer `409` `SNAPSHOTS_DISABLED`; a run already in progress `409` `SNAPSHOT_IN_PROGRESS` with `Retry-After`; a failed run `502` `SNAPSHOT_FAILED`; and a run that outlives the wait `504` `SNAPSHOT_UNCONFIRMED`: it may still land, so read the snapshot status before resending. A resend after a `502` or `504` takes another snapshot. Audited as `snapshot_worker`. `WORKER_NOT_LIVE`, `WORKER_UPGRADE_REQUIRED`, `SNAPSHOTS_DISABLED` and `SNAPSHOT_IN_PROGRESS` release the Idempotency-Key, so a resend after the cause is fixed runs again; a completed answer replays with `Idempotent-Replayed: true`. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. A pending or revoked Worker, or one the fence finds replaced, revoked or removed, answers `409` `WORKER_NOT_LIVE` with `details.status`. A Worker that doesn't advertise the `worker_snapshot_api_v1` capability answers `409` `WORKER_UPGRADE_REQUIRED` with `details.requiredCapability`; upgrade it and retry. Nothing is sent to the Worker for these. A Worker that doesn't answer is `502` `WORKER_UNAVAILABLE`, any answer outside the operation's own is `502` `WORKER_REFUSED`, and a malformed or oversized one is `502` `INVALID_WORKER_RESPONSE`. The Worker's own messages are never answered.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Snapshots` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["workers:operate"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workerId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Snapshot taken | `application/json` | `CreateWorkerSnapshotResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "receipt": {
    "auditEventId": "6a1d3f4e-2b7c-4c8a-9e5f-1d2c3b4a5f60",
    "auditRecorded": true,
    "replayed": false,
    "requestId": "0f6c2f0e-5d1a-4d55-9b0e-4f3b9c2a7d10"
  },
  "snapshot": {
    "degraded": false,
    "excluded": [],
    "objectKey": "worker-snapshots/9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11/20261107T101500.000Z.pgsnap",
    "size": 1048576,
    "skipped": [],
    "snapshotId": "20261107T101500.000Z",
    "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Runs a snapshot on the Worker and waits for it, at most 5 minutes, answering `201` with the run and receipt. The SDK clients give this call a 6-minute request lifetime and never retry its `502` or `504` answers: a resend after `502` `SNAPSHOT_FAILED` or `504` `SNAPSHOT_UNCONFIRMED` takes another snapshot. `409` `SNAPSHOT_IN_PROGRESS` carries `Retry-After` and releases the key.

- Idempotency: required; a completed answer replays with `Idempotent-Replayed: true`.
- After `504` `SNAPSHOT_UNCONFIRMED`, read the snapshot status before resending with a new key.
- Archives are additional objects in the storage destination; the Worker's retention prunes them.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKER_ID:?set POSTGRIP_WORKER_ID to a percent-encoded path value}"
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
const baseUrl = process.env.POSTGRIP_WORKER_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/snapshots");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/snapshots'
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

- [getWorkerSnapshotSettings](./getWorkerSnapshotSettings.md) — Read a worker's snapshot settings
- [getWorkerSnapshotStatus](./getWorkerSnapshotStatus.md) — Read a worker's snapshot status
- [listWorkerSnapshots](./listWorkerSnapshots.md) — List a worker's snapshots
- [updateWorkerSnapshotSettings](./updateWorkerSnapshotSettings.md) — Replace a worker's snapshot settings

[Back to Worker index](./README.md)
