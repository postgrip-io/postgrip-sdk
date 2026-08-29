# Apply an accepted declarative configuration plan

`POST /api/v1/services/configuration-stacks/{stackKey}/plans/{planId}/apply` · `applyPostGripConfigurationPlan` · Service

> Contract bundle `aa2e7e8b6f0156a7234bed7053b7669c9fdd3798f0cb366afafeb1400ccb35b4`
> Service contract `27e286164b9382e283da6de22cbe3c728cb15372363afadf027a8e8795ef19e0`

Revalidates an accepted immutable plan, its digest, policy flags, base stack revision, and live resource ETags before creating one durable aggregate operation. Secret values are accepted only as opaque input-name bindings and are immediately sealed into short-lived Worker commands.

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
| `planId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `ApplyPostGripConfigurationPlanRequest`

```json
{
  "allowAdoption": true,
  "planDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prune": true,
  "secretInputs": {}
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
  "etag": "string",
  "id": "11111111-1111-4111-8111-111111111111",
  "planDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "planId": "11111111-1111-4111-8111-111111111111",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "resources": [
    {
      "etag": "string",
      "path": "string",
      "resourceId": "11111111-1111-4111-8111-111111111111",
      "resourceType": "string"
    }
  ],
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

Revalidates an accepted immutable plan, its digest, policy flags, base stack revision, and live resource ETags before creating one durable aggregate operation. Secret values are accepted only as opaque input-name bindings and are immediately sealed into short-lived Worker commands.

- Idempotency: required.
- A first apply creates the stack at revision zero and advances it only after every action succeeds.
- Poll the operation resource and its paginated action collection; never infer completion from the initial response.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_STACK_KEY:?set POSTGRIP_STACK_KEY to a percent-encoded path value}"
: "${POSTGRIP_PLAN_ID:?set POSTGRIP_PLAN_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "allowAdoption": true,
  "planDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prune": true,
  "secretInputs": {}
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
  "${POSTGRIP_API_URL}/api/v1/services/configuration-stacks/${POSTGRIP_STACK_KEY}/plans/${POSTGRIP_PLAN_ID}/apply" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration-stacks/" + url.PathEscape(os.Getenv("POSTGRIP_STACK_KEY")) + "/plans/" + url.PathEscape(os.Getenv("POSTGRIP_PLAN_ID")) + "/apply")
if err != nil { return err }
body := strings.NewReader("{\"allowAdoption\":true,\"planDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"prune\":true,\"secretInputs\":{}}")
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
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/configuration-stacks/" + encodeURIComponent(process.env.POSTGRIP_STACK_KEY ?? "") + "/plans/" + encodeURIComponent(process.env.POSTGRIP_PLAN_ID ?? "") + "/apply");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"allowAdoption\":true,\"planDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"prune\":true,\"secretInputs\":{}}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration-stacks/' + urllib.parse.quote(os.environ['POSTGRIP_STACK_KEY'], safe='') + '/plans/' + urllib.parse.quote(os.environ['POSTGRIP_PLAN_ID'], safe='') + '/apply'
request = urllib.request.Request(endpoint, data='{"allowAdoption":true,"planDigest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","prune":true,"secretInputs":{}}'.encode(), method='POST')
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

- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection
- [createPostGripConfigurationPlan](./createPostGripConfigurationPlan.md) — Create PostGrip Configuration Plan

[Back to Service index](./README.md)
