# Replace a service application grouping

`PUT /api/v1/services/apps/{appId}` · `updateServiceApp` · Service

> Contract bundle `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`
> Service contract `dd9e4b81913e3757c83c6806500d5bc831f1bd379ca28210c5311f2c79a280bd`

Replaces the application name and description using the application ETag returned by getServiceApp.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Applications` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:write"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `appId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `UpdateServiceAppRequest`

```json
{
  "name": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Service application updated | `application/json` | `ServiceAppMutationResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "app": {
    "createdAt": "2026-01-01T00:00:00Z",
    "etag": "string",
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "string",
    "updatedAt": "2026-01-01T00:00:00Z",
    "version": 1
  },
  "catalogRevision": 1,
  "configurationRevision": 1,
  "effect": "immediate",
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

Replaces the name and description of one application grouping under its configuration ETag.

- Supply the application ETag as If-Match.
- Idempotency: required.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_APP_ID:?set POSTGRIP_APP_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "name": "string"
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
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/apps/${POSTGRIP_APP_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/apps/" + url.PathEscape(os.Getenv("POSTGRIP_APP_ID")))
if err != nil { return err }
body := strings.NewReader("{\"name\":\"string\"}")
request, err := http.NewRequestWithContext(ctx, "PUT", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")
request.Header.Set("Idempotency-Key", os.Getenv("POSTGRIP_IDEMPOTENCY_KEY"))
request.Header.Set("If-Match", os.Getenv("POSTGRIP_IF_MATCH"))
client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/apps/" + encodeURIComponent(process.env.POSTGRIP_APP_ID ?? ""));

const response = await fetch(url, {
  method: "PUT",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, },
  body: "{\"name\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/apps/' + urllib.parse.quote(os.environ['POSTGRIP_APP_ID'], safe='')
request = urllib.request.Request(endpoint, data='{"name":"string"}'.encode(), method='PUT')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')
request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
request.add_header('If-Match', os.environ["POSTGRIP_IF_MATCH"])
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [createServiceApp](./createServiceApp.md) — Create a service application
- [deleteServiceApp](./deleteServiceApp.md) — Delete a service application
- [getServiceApp](./getServiceApp.md) — Get a service application
- [listServiceApps](./listServiceApps.md) — List service applications

[Back to Service index](./README.md)
