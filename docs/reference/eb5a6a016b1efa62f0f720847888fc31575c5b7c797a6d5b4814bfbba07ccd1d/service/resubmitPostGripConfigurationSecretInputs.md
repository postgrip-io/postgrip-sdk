# Resubmit expired declarative secret inputs

`POST /api/v1/services/configuration-stacks/{stackKey}/operations/{operationId}/secret-inputs` · `resubmitPostGripConfigurationSecretInputs` · Service

> Contract bundle `eb5a6a016b1efa62f0f720847888fc31575c5b7c797a6d5b4814bfbba07ccd1d`
> Service contract `74d48490b3cf7b7fc4962124d2d5a9a0432dcf384e6ec4b877872118a9f2044b`

Replaces only the expired secret inputs named by blocked operation actions. Each value is immediately sealed into the existing short-lived Worker command path and is never returned by any read API.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
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
| `stackKey` | path | yes | `string` | `"recorded"` | — |
| `operationId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `ResubmitPostGripConfigurationSecretInputsRequest`

```json
{
  "secretInputs": {
    "recorded": "string"
  }
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Successful response | `application/json` | `PostGripConfigurationStackOperation` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "attemptCount": 1,
  "baseStackRevision": 1,
  "configurationVersion": 1,
  "createdAt": "2026-01-01T00:00:00Z",
  "id": "11111111-1111-4111-8111-111111111111",
  "planDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "planId": "11111111-1111-4111-8111-111111111111",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "stackId": "11111111-1111-4111-8111-111111111111",
  "stackKey": "string",
  "state": "pending",
  "summary": {
    "applying": 1,
    "blocked": 1,
    "failed": 1,
    "pending": 1,
    "skipped": 1,
    "succeeded": 1,
    "total": 1
  },
  "updatedAt": "2026-01-01T00:00:00Z"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Replaces only the expired secret inputs named by blocked operation actions. Each value is immediately sealed into the existing short-lived Worker command path and is never returned by any read API.

- Idempotency and If-Match are required.
- Read the blocked action pages to discover the exact opaque input identifiers and versions before submitting replacements.
- Send request bodies from a protected file or standard input; do not place secret values in shell arguments.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_STACK_KEY:?set POSTGRIP_STACK_KEY to a percent-encoded path value}"
: "${POSTGRIP_OPERATION_ID:?set POSTGRIP_OPERATION_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "secretInputs": {
    "recorded": "string"
  }
}
POSTGRIP_JSON
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  POST \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/configuration-stacks/${POSTGRIP_STACK_KEY}/operations/${POSTGRIP_OPERATION_ID}/secret-inputs" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration-stacks/" + url.PathEscape(os.Getenv("POSTGRIP_STACK_KEY")) + "/operations/" + url.PathEscape(os.Getenv("POSTGRIP_OPERATION_ID")) + "/secret-inputs")
if err != nil { return err }
body := strings.NewReader("{\"secretInputs\":{\"recorded\":\"string\"}}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
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
const url = new URL(baseUrl + "/api/v1/services/configuration-stacks/" + encodeURIComponent(process.env.POSTGRIP_STACK_KEY ?? "") + "/operations/" + encodeURIComponent(process.env.POSTGRIP_OPERATION_ID ?? "") + "/secret-inputs");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, },
  body: "{\"secretInputs\":{\"recorded\":\"string\"}}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration-stacks/' + urllib.parse.quote(os.environ['POSTGRIP_STACK_KEY'], safe='') + '/operations/' + urllib.parse.quote(os.environ['POSTGRIP_OPERATION_ID'], safe='') + '/secret-inputs'
request = urllib.request.Request(endpoint, data='{"secretInputs":{"recorded":"string"}}'.encode(), method='POST')
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

- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection
- [createPostGripConfigurationPlan](./createPostGripConfigurationPlan.md) — Create PostGrip Configuration Plan

[Back to Service index](./README.md)
