# Queue a bounded worker-host upgrade

`POST /api/v1/workers/{workerId}/upgrade` · `upgradeWorker` · Worker

> Contract bundle `98c8ed10e0ecb902c68c9ffabcb6ba943ab3e2a2aafac9f9abe70d74268db6a9`
> Worker contract `afb2f195907615f4b3de7f9615c66c24ca6a90c7f14ac98d446337bd0779e432`

Uses the contract-defined POST /api/v1/workers/{workerId}/upgrade behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Workers` |
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
| `202` | Upgrade queued | `application/json` | `UpgradeWorkerResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "expectedSignerVersion": 1,
  "expectedVersion": 1,
  "lifecycleDirective": "upgrade",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "signerImage": "string",
  "status": "queued",
  "worker": {
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
  },
  "workerImage": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined POST /api/v1/workers/{workerId}/upgrade behavior.

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
  "${POSTGRIP_API_URL}/api/v1/workers/${POSTGRIP_WORKER_ID}/upgrade" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers/" + url.PathEscape(os.Getenv("POSTGRIP_WORKER_ID")) + "/upgrade")
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
const url = new URL(baseUrl + "/api/v1/workers/" + encodeURIComponent(process.env.POSTGRIP_WORKER_ID ?? "") + "/upgrade");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers/' + urllib.parse.quote(os.environ['POSTGRIP_WORKER_ID'], safe='') + '/upgrade'
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

- [checkWorker](./checkWorker.md) — Check worker connectivity and trust
- [createWorker](./createWorker.md) — Create a pending Worker with client-owned bootstrap material
- [getWorker](./getWorker.md) — Get a worker
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance

[Back to Worker index](./README.md)
