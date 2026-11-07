# Replace a worker's snapshot settings

`PUT /api/v1/workers/{workerId}/snapshot/settings` · `updateWorkerSnapshotSettings` · Worker

> Contract bundle `20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`
> Worker contract `86004c9dd3c7b8cf629e47141a53e4fcfb97f633294b96a68bec1c67f957fcce`

Replaces the whole settings record: every field but `enabled` takes its zero value when omitted, so read the settings and send them back to change one field. `storageDestinationId` names a storage destination of the organization, required to enable snapshots; the bucket coordinates come from that destination, and its credentials must already be delivered to the Worker from the console's Storage page. `signingKey` is write-only: omit it to keep the stored key. Unknown fields answer `400` `INVALID_BODY`; a destination the organization doesn't have, a missing `enabled`, a `retentionCount` below 1 with `enabled` (refused before the Worker is contacted) or settings the Worker refuses answer `400` `VALIDATION`. `details.field`, where one is known, is one of `enabled`, `storageDestinationId`, `cron`, `retentionCount`, `volumeMaxBytes`, `recipientPublicKey` or `signingKey`, and `message` is PostGrip's own text for it. A Worker refusal names its field when the Worker reports one: `storageDestinationId` also covers the destination's bucket settings, which come from the destination. A Worker too old to report one answers without `details.field`. The write is unconditional: no precondition is taken. Answers the settings as the Worker then reads them. Audited as `configure_worker_snapshots`, never with the signing key. `WORKER_NOT_LIVE`, `WORKER_UPGRADE_REQUIRED`, `SNAPSHOTS_DISABLED` and `SNAPSHOT_IN_PROGRESS` release the Idempotency-Key, so a resend after the cause is fixed runs again; a completed answer replays with `Idempotent-Replayed: true`. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. A pending or revoked Worker, or one the fence finds replaced, revoked or removed, answers `409` `WORKER_NOT_LIVE` with `details.status`. A Worker that doesn't advertise the `worker_snapshot_api_v1` capability answers `409` `WORKER_UPGRADE_REQUIRED` with `details.requiredCapability`; upgrade it and retry. Nothing is sent to the Worker for these. A Worker that doesn't answer is `502` `WORKER_UNAVAILABLE`, any answer outside the operation's own is `502` `WORKER_REFUSED`, and a malformed or oversized one is `502` `INVALID_WORKER_RESPONSE`. The Worker's own messages are never answered.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Snapshots` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["workers:admin"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workerId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `UpdateWorkerSnapshotSettingsRequest`

```json
{
  "cron": "0 3 * * *",
  "enabled": true,
  "recipientPublicKey": "replace-with-base64-x25519-public-key",
  "retentionCount": 7,
  "storageDestinationId": "3c0f1e2d-8a7b-4c6d-9e1f-0a2b3c4d5e6f",
  "volumeMaxBytes": 0,
  "volumesEnabled": false,
  "volumesHot": false
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Snapshot settings saved | `application/json` | `UpdateWorkerSnapshotSettingsResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "settings": {
    "enabled": true,
    "hasSigningKey": true,
    "volumesEnabled": true,
    "volumesHot": true,
    "workerId": "11111111-1111-4111-8111-111111111111"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Replaces the whole settings record: every field but `enabled` takes its zero value when omitted, so read the settings and send them back to change one field. `signingKey` is write-only: omit it to keep the stored key; no answer carries it. Answers the settings as the Worker then reads them, with the receipt.

- Idempotency: required; the replay record never holds the signing key.
- Never log or print the request body when it carries `signingKey`.
- Restore the fixture Worker's previous settings after the test.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKER_ID:?set POSTGRIP_WORKER_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "cron": "0 3 * * *",
  "enabled": true,
  "recipientPublicKey": "replace-with-base64-x25519-public-key",
  "retentionCount": 7,
  "storageDestinationId": "3c0f1e2d-8a7b-4c6d-9e1f-0a2b3c4d5e6f",
  "volumeMaxBytes": 0,
  "volumesEnabled": false,
  "volumesHot": false
}
POSTGRIP_JSON
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  PUT \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}/snapshot/settings" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")) + "/snapshot/settings")
if err != nil { return err }
body := strings.NewReader("{\"cron\":\"0 3 * * *\",\"enabled\":true,\"recipientPublicKey\":\"replace-with-base64-x25519-public-key\",\"retentionCount\":7,\"storageDestinationId\":\"3c0f1e2d-8a7b-4c6d-9e1f-0a2b3c4d5e6f\",\"volumeMaxBytes\":0,\"volumesEnabled\":false,\"volumesHot\":false}")
request, err := http.NewRequestWithContext(ctx, "PUT", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")
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
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/snapshot/settings");

const response = await fetch(url, {
  method: "PUT",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"cron\":\"0 3 * * *\",\"enabled\":true,\"recipientPublicKey\":\"replace-with-base64-x25519-public-key\",\"retentionCount\":7,\"storageDestinationId\":\"3c0f1e2d-8a7b-4c6d-9e1f-0a2b3c4d5e6f\",\"volumeMaxBytes\":0,\"volumesEnabled\":false,\"volumesHot\":false}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/snapshot/settings'
request = urllib.request.Request(endpoint, data='{"cron":"0 3 * * *","enabled":true,"recipientPublicKey":"replace-with-base64-x25519-public-key","retentionCount":7,"storageDestinationId":"3c0f1e2d-8a7b-4c6d-9e1f-0a2b3c4d5e6f","volumeMaxBytes":0,"volumesEnabled":false,"volumesHot":false}'.encode(), method='PUT')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')
request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
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
- [listStorageDestinations](./listStorageDestinations.md) — List storage destinations
- [listWorkerSnapshots](./listWorkerSnapshots.md) — List a worker's snapshots

[Back to Worker index](./README.md)
