# Remove a worker

`DELETE /api/v1/workers/{workerId}` · `removeWorker` · Worker

> Contract bundle `9b1659218aa56bbbf542bf55d9475c7cf16ae036b531c72c099adc738203d439`
> Worker contract `40a51d3084dc368881b163637b025f45bb412f6d3525d3caf2842dbda1706460`

Removes the Worker as the console's Remove Worker dialog does, after confirming that the removal impact is still the one you read. Send `getWorkerRemovalImpact`'s `etag` as `If-Match`; without one the request answers `428` `PRECONDITION_REQUIRED`. The removal holds the Worker and reads its impact again before it deletes anything: an impact that has changed since, or an `If-Match` of `*`, answers `412` `PRECONDITION_FAILED` and nothing is changed; read the impact again and decide again. In one transaction the removal deletes the Worker's services and its exclusive deploy projects, unassigns the kept projects' environments from it, clears it as a project default, and deletes or retires the Worker. A Worker that has enrolled keeps its record, marked removed, until its next heartbeat tells its container and attestation signer to stop (`shutdownRequested: true`); the record is deleted 24 hours later. A Worker that never enrolled is deleted at once. After the commit PostGrip removes what the Worker held of those services, their deploy domains and their repository and enterprise runner credentials from the Worker, counted in `workerCleanup`; a revoked or replaced Worker is sent nothing, and those cleanups are counted `skipped`. The Worker host keeps its Docker volumes and Cloudflared; delete the host yourself. A Worker with any managed volume, a lost Worker's unreachable ones included, answers `409` `WORKER_HAS_MANAGED_VOLUMES` and nothing is changed. The request takes no body: one answers `400` `INVALID_BODY`. A Worker the tenant doesn't have, or a removed one, answers `404` `NOT_FOUND`. A failed step answers `500` `DB_ERROR` with everything rolled back. Audited as `delete_worker`, with the token as the actor. Every answer but `408`, `429`, `502`, `503` and `504` is kept for the Idempotency-Key for 24 hours, refusals included: a resend with the same key replays it with `Idempotent-Replayed: true` and never removes twice. The key does not cover `If-Match`, so after a refusal send the removal again with a new key.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Workers` |
| Operation class | `tenant-api` |
| Safety | `destructive` |
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
| `If-Match` | header | yes | `string` | `"string"` | The `etag` of the Worker's removal impact (`getWorkerRemovalImpact`). |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Worker removed | `application/json` | `RemoveWorkerResponse` |
| `409` | Conflict. `WORKER_HAS_MANAGED_VOLUMES`: the Worker still owns managed volumes; delete or move them, read the removal impact again and send the removal with a new Idempotency-Key. Nothing is changed. `IDEMPOTENCY_CONFLICT` and `IDEMPOTENCY_IN_PROGRESS` also use this status. | `application/json` | `ErrorResponse` |
| `412` | `PRECONDITION_FAILED`: the removal impact has changed since the one `If-Match` names. Nothing is changed; read the impact again. | `application/json` | `ErrorResponse` |
| `428` | `PRECONDITION_REQUIRED`: the request has no `If-Match`. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "clearedProjectDefaultCount": 1,
  "deletedProjectCount": 1,
  "deletedServiceCount": 2,
  "keptProjectCount": 1,
  "receipt": {
    "auditEventId": "0e6f1c2a-8b4d-4f7e-9a3c-5d2b7e1f4a60",
    "auditRecorded": true,
    "replayed": false,
    "requestId": "req_01"
  },
  "shutdownRequested": true,
  "unassignedEnvironmentCount": 1,
  "workerCleanup": {
    "attempted": 4,
    "failed": 0,
    "skipped": 0
  },
  "workerId": "9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined DELETE /api/v1/workers/{workerId} behavior.

- Idempotency: required.
- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKER_ID:?set POSTGRIP_WORKER_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  DELETE \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
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
request, err := http.NewRequestWithContext(ctx, "DELETE", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))

request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
request.Header.Set("If-Match", os.Getenv("POSTGRIP_IF_MATCH"))
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
  method: "DELETE",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='')
request = urllib.request.Request(endpoint, method='DELETE')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")

request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
request.add_header('If-Match', os.environ["POSTGRIP_IF_MATCH"])
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
- [getWorkerRemovalImpact](./getWorkerRemovalImpact.md) — Preview a worker's removal
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance

[Back to Worker index](./README.md)
