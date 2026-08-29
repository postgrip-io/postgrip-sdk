# Create a pending Worker

`POST /api/v1/workers` · `createWorker` · Worker

> Contract bundle `d9e50199dc1cda4d3f54d754e65fb72c5aad6f9e4e51894bb97f0bb5c567fe3c`
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

## Typed SDK bootstrap workflow

The generic raw snippets are intentionally omitted for this operation: a reliable caller must persist the bootstrap values and idempotency key before the request.
Use the typed Go, TypeScript, or Python Worker client with the durable journal workflow in [`docs/worker-bootstrap.md`](../../../worker-bootstrap.md).


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
with open(source, "rb") as stream:
    os.fsync(stream.fileno())
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

## Raw HTTP omission

Generic raw language snippets are intentionally omitted because they cannot demonstrate the required crash-safe pre-request journal. Use the durable cURL workflow above or the typed SDK bootstrap workflow.

## Related operations

- [checkWorker](./checkWorker.md) — Check worker connectivity and trust
- [getWorker](./getWorker.md) — Get a worker
- [listWorkerAssignments](./listWorkerAssignments.md) — List worker assignments
- [listWorkers](./listWorkers.md) — List workers
- [placeWorkerInMaintenance](./placeWorkerInMaintenance.md) — Place a worker in maintenance
- [resumeWorkerFromMaintenance](./resumeWorkerFromMaintenance.md) — Resume a worker from maintenance
- [upgradeWorker](./upgradeWorker.md) — Queue a bounded worker-host upgrade

[Back to Worker index](./README.md)
