# Rotate a service token

`POST /api/v1/services/project/{serviceId}/token/rotate` · `rotateServiceToken` · Service

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Service contract `95872979a1e84bd2915f33ce6c2326aec2e0cf77ba2e474f65e08d619efbe439`

Makes a new bearer token for a ZVEC, LadybugDB or NodeDB service and stores it as its production environment's secret variable `POSTGRIP_SERVICE_AUTH_TOKEN`, creating the variable, or making it secret, when needed. The token is `pgsvc_` followed by 43 base64url characters, the console's format. Storing it queues one configuration operation for the environment's Worker, `configurationOperationId`, as putServiceVariableValue does. Once that operation has succeeded, PostGrip redeploys the environment's latest deployment, fenced on it, even if the caller has gone away: follow `rotation.state` with getServiceTokenRotation. The old token keeps working until that redeployment is ready. The token is only in this answer. A replay of the same Idempotency-Key answers the same rotation with `token` `null`: PostGrip keeps no copy it can show, so if the first answer was lost, rotate again with a new key. Without `If-Match` the rotation replaces whatever token the environment has; with it, it must be the `etag` of the environment's `POSTGRIP_SERVICE_AUTH_TOKEN` variable, as listServiceVariables answers it.

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
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | no | `string` | `"string"` | Optional: the `etag` of the environment's `POSTGRIP_SERVICE_AUTH_TOKEN` variable, as listServiceVariables answers it. The token is replaced only while the variable still has that ETag. |

## Request body

Content type: `application/json` · Schema: `ServiceTokenRotateRequest`

```json
{
  "environmentId": "11111111-1111-4111-8111-111111111111"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Accepted: the token is stored once the configuration operation succeeds, and the redeploy follows. `token` is set only in this answer; a replay answers `null`. | `application/json` | `ServiceTokenRotationResponse` |
| `404` | Not found. `SERVICE_NOT_FOUND`: `serviceId` or `environmentId` is not a UUID, or names no service or environment of the tenant. | `application/json` | `ErrorResponse` |
| `409` | Conflict. `SERVICE_OPERATION_NOT_SUPPORTED`: the service is not a ZVEC, LadybugDB or NodeDB service, whose runtime reads the token, or `environmentId` names an environment that is not `production`. `SERVICE_ENVIRONMENT_REQUIRED`: without `environmentId`, the service has no production environment or more than one. `SERVICE_STATE_CHANGED`: the environment has no assigned Worker. `WORKER_UPGRADE_REQUIRED` (`details.workerId`, `details.requiredCapability`): the Worker must be upgraded first; this refusal is not stored against the Idempotency-Key. `IDEMPOTENCY_CONFLICT` and `IDEMPOTENCY_IN_PROGRESS` also use this status. | `application/json` | `ErrorResponse` |
| `412` | Precondition failed. `PRECONDITION_FAILED`: `If-Match` is not the token variable's current `etag` (`details.currentVersion`), or the environment has no `POSTGRIP_SERVICE_AUTH_TOKEN` variable to match (`details.currentVersion` `0`). Nothing changed. | `application/json` | `ErrorResponse` |
| `503` | Unavailable. Nothing changed. `AUDIT_UNAVAILABLE`: the rotation could not be recorded for audit. `TOKEN_GENERATION_FAILED`: no random token could be made. `CONFIGURATION_UNAVAILABLE`: the configuration store is unavailable. `IDEMPOTENCY_UNAVAILABLE` with the message that the operation completed but its replay result could not be stored means the rotation ran and its token is lost: rotate again with a new key. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "rotation": {
    "attemptCount": 1,
    "completedAt": "2026-01-01T00:00:00Z",
    "configurationOperationId": "11111111-1111-4111-8111-111111111111",
    "configurationOperationState": "string",
    "createdAt": "2026-01-01T00:00:00Z",
    "deploymentId": "11111111-1111-4111-8111-111111111111",
    "environmentId": "11111111-1111-4111-8111-111111111111",
    "errorCode": "string",
    "expectedLatestDeploymentId": "11111111-1111-4111-8111-111111111111",
    "id": "11111111-1111-4111-8111-111111111111",
    "serviceId": "11111111-1111-4111-8111-111111111111",
    "state": "configuring",
    "updatedAt": "2026-01-01T00:00:00Z",
    "variableId": "11111111-1111-4111-8111-111111111111"
  },
  "token": "pgsvc_recordedxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "variable": {
    "createdAt": "2026-01-01T00:00:00Z",
    "etag": "string",
    "hasValue": true,
    "id": "11111111-1111-4111-8111-111111111111",
    "isSecret": true,
    "name": "string",
    "updatedAt": "2026-01-01T00:00:00Z",
    "version": 1
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Makes a new pgsvc_ bearer token for a ZVEC, LadybugDB or NodeDB service, stores it as its production environment's secret variable POSTGRIP_SERVICE_AUTH_TOKEN through one configuration operation, and once that succeeds redeploys the environment's latest deployment, fenced on it, server-side. The 202 answer carries the token only the first time: a replay of the same Idempotency-Key answers token null, and PostGrip keeps no copy, so a lost answer is not recoverable by retrying; rotate again with a new key. The old token works until the redeployment is ready.

- Idempotency: required.
- If-Match: optional (the token variable's ETag from listServiceVariables).
- Never log or record the token; use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "environmentId": "11111111-1111-4111-8111-111111111111"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/token/rotate" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/token/rotate")
if err != nil { return err }
body := strings.NewReader("{\"environmentId\":\"11111111-1111-4111-8111-111111111111\"}")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/token/rotate");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"environmentId\":\"11111111-1111-4111-8111-111111111111\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/token/rotate'
request = urllib.request.Request(endpoint, data='{"environmentId":"11111111-1111-4111-8111-111111111111"}'.encode(), method='POST')
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

- [abandonServiceConfigurationOperation](./abandonServiceConfigurationOperation.md) — Abandon Service Configuration Operation
- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value

[Back to Service index](./README.md)
