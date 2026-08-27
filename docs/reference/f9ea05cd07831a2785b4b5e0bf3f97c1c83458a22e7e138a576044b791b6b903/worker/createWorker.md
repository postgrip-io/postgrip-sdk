# Create a pending Worker

`POST /api/v1/workers` · `createWorker` · Worker

> Contract bundle `f9ea05cd07831a2785b4b5e0bf3f97c1c83458a22e7e138a576044b791b6b903`
> Worker contract `afb2f195907615f4b3de7f9615c66c24ca6a90c7f14ac98d446337bd0779e432`

The caller must durably store the write-only bootstrap values and Idempotency-Key before sending this request. The response never returns either bootstrap value.

## Operation

| Field | Value |
| --- | --- |
| Plane | `worker` |
| Resource tags | `Workers` |
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
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `CreateWorkerRequest`

```json
{
  "autoShutdownOnRemoval": true,
  "bootstrap": {
    "attestationBootstrapToken": "stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "enrollmentKey": "stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  "host": "https://worker.example.com",
  "name": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Pending Worker created | `application/json` | `CreateWorkerResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "bootstrap": {
    "attestationExpiresAt": "2026-01-01T00:00:00Z",
    "enrollmentExpiresAt": "2026-01-01T00:00:00Z"
  },
  "etag": "string",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
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
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Creates one pending Worker from caller-generated write-only enrollment and attestation bootstrap values. The server persists only their hashes, derives the signer identity, returns a safe Worker projection plus ETag and expiries, and replays the exact response for the same idempotency key and body.

- Persist the bootstrap values and idempotency key in an operator-approved mode-0600 store before the request.
- Idempotency: required; a replay does not extend either bootstrap expiry.
- Never log or print the request body and remove consumed values only after trusted enrollment.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_API_URL="${POSTGRIP_WORKER_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or POSTGRIP_WORKER_URL}"
: "${POSTGRIP_WORKER_NAME:?set the pending Worker name}"
: "${POSTGRIP_WORKER_HOST:?set the Worker HTTPS origin}"
: "${POSTGRIP_BOOTSTRAP_STATE:?set an approved durable secret-state path}"
: "${POSTGRIP_WORKER_RECEIPT:?set a durable safe-receipt path}"
export POSTGRIP_WORKER_NAME POSTGRIP_WORKER_HOST POSTGRIP_BOOTSTRAP_STATE

# Exclusively persist caller-owned values and the replay key before POST.
python3 <<'PY'
import base64, hashlib, json, os, secrets, stat
path = os.path.abspath(os.environ["POSTGRIP_BOOTSTRAP_STATE"])
parent = os.path.dirname(path)
parent_mode = stat.S_IMODE(os.stat(parent).st_mode)
if parent_mode & 0o022 and not parent_mode & stat.S_ISVTX:
    raise SystemExit("bootstrap-state parent must not be group/world writable")
if os.path.lexists(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise SystemExit("existing bootstrap state must be a regular mode-0600 file")
    with open(path, encoding="utf-8") as stream:
        state = json.load(stream)
    if state.get("schemaVersion") != "postgrip.worker-create-curl/v1":
        raise SystemExit("existing bootstrap state has the wrong schema")
else:
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    request = {
        "name": os.environ["POSTGRIP_WORKER_NAME"],
        "host": os.environ["POSTGRIP_WORKER_HOST"].rstrip("/"),
        "autoShutdownOnRemoval": True,
        "bootstrap": {
            "enrollmentKey": encode(secrets.token_bytes(32)),
            "attestationBootstrapToken": encode(secrets.token_bytes(32)),
        },
    }
    canonical = json.dumps(request, separators=(",", ":"), sort_keys=True).encode()
    state = {
        "schemaVersion": "postgrip.worker-create-curl/v1",
        "idempotencyKey": "postgrip-worker-create-" + secrets.token_hex(16),
        "canonicalRequestDigest": hashlib.sha256(canonical).hexdigest(),
        "request": request,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, json.dumps(state, indent=2, sort_keys=True).encode() + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
PY

POSTGRIP_BODY_FILE="$(mktemp "$(dirname "${POSTGRIP_BOOTSTRAP_STATE}")/.postgrip-worker-request.XXXXXX")"
response_file="$(mktemp "$(dirname "${POSTGRIP_WORKER_RECEIPT}")/.postgrip-worker-response.XXXXXX")"
trap 'rm -f "${POSTGRIP_BODY_FILE}" "${response_file}"' EXIT
chmod 600 "${POSTGRIP_BODY_FILE}" "${response_file}"
POSTGRIP_IDEMPOTENCY_KEY="$(python3 - "${POSTGRIP_BOOTSTRAP_STATE}" "${POSTGRIP_BODY_FILE}" <<'PY'
import json, os, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    state = json.load(stream)
with open(sys.argv[2], "w", encoding="utf-8") as stream:
    json.dump(state["request"], stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(state["idempotencyKey"])
PY
)"

curl \
  --config \
  - \
  --fail-with-body --silent --show-error \
  --max-redirs 0 \
  --connect-timeout 5 --max-time 30 --max-filesize 1048576 \
  --request POST --header 'Content-Type: application/json' \
  --header "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --data-binary "@${POSTGRIP_BODY_FILE}" --output "${response_file}" \
  "${POSTGRIP_API_URL}/api/v1/workers" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF

# Atomically retain the safe Worker ID/ETag/expiries for the next bootstrap step.
python3 - "${response_file}" "${POSTGRIP_WORKER_RECEIPT}" <<'PY'
import json, os, stat, sys
source, target = sys.argv[1], os.path.abspath(sys.argv[2])
with open(source, encoding="utf-8") as stream:
    receipt = json.load(stream)
if not receipt.get("worker", {}).get("id") or not receipt.get("etag"):
    raise SystemExit("Worker response omitted its safe receipt")
os.chmod(source, 0o600)
os.replace(source, target)
directory = os.open(os.path.dirname(target), os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
python3 - "${POSTGRIP_WORKER_RECEIPT}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    receipt = json.load(stream)
print(json.dumps({"workerId": receipt["worker"]["id"], "etag": receipt["etag"], "bootstrap": receipt["bootstrap"]}, separators=(",", ":")))
PY
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_WORKER_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workers")
if err != nil { return err }
body := strings.NewReader("{\"autoShutdownOnRemoval\":true,\"bootstrap\":{\"attestationBootstrapToken\":\"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",\"enrollmentKey\":\"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"},\"host\":\"https://worker.example.com\",\"name\":\"string\"}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/workers");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"autoShutdownOnRemoval\":true,\"bootstrap\":{\"attestationBootstrapToken\":\"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",\"enrollmentKey\":\"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"},\"host\":\"https://worker.example.com\",\"name\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_WORKER_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workers'
request = urllib.request.Request(endpoint, data='{"autoShutdownOnRemoval":true,"bootstrap":{"attestationBootstrapToken":"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","enrollmentKey":"stringxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},"host":"https://worker.example.com","name":"string"}'.encode(), method='POST')
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

- [checkWorker](./checkWorker.md) — Check worker connectivity and trust
- [getWorker](./getWorker.md) — Get a worker
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance
- [upgradeWorker](./upgradeWorker.md) — Queue a bounded worker-host upgrade

[Back to Worker index](./README.md)
