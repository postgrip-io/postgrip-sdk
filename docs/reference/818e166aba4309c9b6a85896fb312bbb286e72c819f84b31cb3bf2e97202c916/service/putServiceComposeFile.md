# Replace an environment Compose override

`PUT /api/v1/services/project/{serviceId}/environments/{environmentId}/compose` · `putServiceComposeFile` · Service

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Service contract `95872979a1e84bd2915f33ce6c2326aec2e0cf77ba2e474f65e08d619efbe439`

Validates and replaces the Worker-held Compose override. This administrative operation can materially change workload execution. Without `If-Match` the write is unconditional. With `If-Match` set to the `etag` getServiceComposeFile answered, the file is replaced only if it has not changed since: otherwise `412` `PRECONDITION_FAILED`, and nothing is written. A conditional write needs a Worker with versioned Compose files, the ones whose read answers an `etag`; an older Worker answers `409` `WORKER_UPGRADE_REQUIRED`. When the write's answer is lost, `409` `WRITE_OUTCOME_UNKNOWN`: read the file again before retrying. The new `etag` is only in the answer in hand: a replay of the same Idempotency-Key answers the file without `etag` and with no `ETag` header, so read the file again for its ETag. An `If-Match` that is not one Compose ETag answers `400` `VALIDATION`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Configuration` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:admin"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `environmentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | no | `string` | `"string"` | Optional: the Compose file's `etag`, as getServiceComposeFile answers it. The file is replaced only while it still has that ETag. |

## Request body

Content type: `application/json` · Schema: `PutServiceComposeFileRequest`

```json
{
  "content": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response. A conditional write answers the file's new `etag`, in `compose.etag` and the `ETag` header; an unconditional one, and a replay of either, answers none. | `application/json` | `ServiceComposeMutationResponse` |
| `404` | Not found. `SERVICE_NOT_FOUND`: `serviceId` or `environmentId` is not a UUID, or names no service or environment of the tenant. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "compose": {
    "content": "string",
    "envId": "11111111-1111-4111-8111-111111111111",
    "projectId": "11111111-1111-4111-8111-111111111111"
  },
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Validates and replaces the Worker-held Compose override for one exact service environment.

- Idempotency: required.
- This can materially change workload execution and must be explicitly confirmed by automation.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_ENVIRONMENT_ID:?set POSTGRIP_ENVIRONMENT_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "content": "string"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/compose" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/compose")
if err != nil { return err }
body := strings.NewReader("{\"content\":\"string\"}")
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
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/compose");

const response = await fetch(url, {
  method: "PUT",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"content\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/compose'
request = urllib.request.Request(endpoint, data='{"content":"string"}'.encode(), method='PUT')
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

- [deleteServiceComposeFile](./deleteServiceComposeFile.md) — Delete Environment Compose File
- [exportServiceVariables](./exportServiceVariables.md) — Export Environment Variables
- [getServiceComposeFile](./getServiceComposeFile.md) — Get Environment Compose File

[Back to Service index](./README.md)
