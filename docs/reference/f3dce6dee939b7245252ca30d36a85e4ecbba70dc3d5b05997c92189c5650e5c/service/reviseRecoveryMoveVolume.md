# Revise Recovery Move Volume

`POST /api/v1/services/project/{serviceId}/environments/{environmentId}/recovery-moves/{moveId}/volumes/{volumeRef}` · `reviseRecoveryMoveVolume` · Service

> Contract bundle `f3dce6dee939b7245252ca30d36a85e4ecbba70dc3d5b05997c92189c5650e5c`
> Service contract `896e341335e4fccd8b6cf94c535eae2025d65103b8af6b713fa31911cc0be584`

Repairs one volume of a committed recovery move, fenced by `If-Match` on the record's ETag. Only an `adopt-on-destination` volume whose step is `failed` or `pending`, of an open record whose environment is still on the move's destination, is revised, to `recreate-empty` or `replace-with`. In one transaction it holds the destination as a placement target, ends the destination's adoption operation as `superseded`, abandons the volume's migration and managed-volume records (deleting nothing on any host), binds the new volume (provisioned empty, or the named replacement) and stages its operation. It acts on the record and never re-evaluates whether the original source is lost: a new reassignment cannot repair the move, because its source, the destination, is live and its pending adoption refuses an ordinary reassignment. Refusals write nothing.

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
| `environmentId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `moveId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `volumeRef` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `ReviseRecoveryMoveVolumeRequest`

```json
{
  "disposition": "recreate-empty"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceRecoveryMoveRevisionResponse` |
| `409` | Conflict. `RECOVERY_STEP_NOT_REVISABLE`: the volume is not an `adopt-on-destination` volume whose step is `failed` or `pending`, or the record is closed (`details.disposition`, `details.stepState`, `details.closed`). `SERVICE_STATE_CHANGED`: the environment is no longer on the move's destination. `WORKER_REVOKED`: the destination was revoked after the move (`details.workerId`); a destination removed or replaced since answers `404` `NOT_FOUND`. `WORKER_UNAVAILABLE`: the destination has lost its session and cannot accept the staged operation (`details.workerId`); recovery-move the environment off it first. This refusal is not stored against the Idempotency-Key, so a retry with the same key runs again. `VOLUME_BINDING_CONFLICT`: the replacement is not available on the destination. Other conflicts on this route also use this status. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "recoveryMove": {
    "configurationOperationId": "11111111-1111-4111-8111-111111111111",
    "createdAt": "2026-01-01T00:00:00Z",
    "destinationWorkerId": "11111111-1111-4111-8111-111111111111",
    "environmentId": "11111111-1111-4111-8111-111111111111",
    "etag": "string",
    "id": "11111111-1111-4111-8111-111111111111",
    "sourceWorkerId": "11111111-1111-4111-8111-111111111111",
    "state": "open",
    "updatedAt": "2026-01-01T00:00:00Z",
    "version": 1,
    "volumes": [
      {
        "boundVolumeRef": "11111111-1111-4111-8111-111111111111",
        "containerPath": "string",
        "disposition": "adopt-on-destination",
        "readOnly": true,
        "stepState": "pending",
        "volumeRef": "11111111-1111-4111-8111-111111111111"
      }
    ]
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Repairs one failed or pending adopt-on-destination volume of a committed recovery move to recreate-empty or replace-with, fenced by If-Match on the record. The destination is re-checked under the placement lock; a revoked, removed or session-lost destination is refused and nothing is written. It never re-evaluates the original source.

- Idempotency: required.
- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_SERVICE_ID:?set POSTGRIP_SERVICE_ID to a percent-encoded path value}"
: "${POSTGRIP_ENVIRONMENT_ID:?set POSTGRIP_ENVIRONMENT_ID to a percent-encoded path value}"
: "${POSTGRIP_MOVE_ID:?set POSTGRIP_MOVE_ID to a percent-encoded path value}"
: "${POSTGRIP_VOLUME_REF:?set POSTGRIP_VOLUME_REF to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "disposition": "recreate-empty"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/recovery-moves/${POSTGRIP_MOVE_ID}/volumes/${POSTGRIP_VOLUME_REF}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/recovery-moves/" + url.PathEscape(os.Getenv("POSTGRIP_MOVE_ID")) + "/volumes/" + url.PathEscape(os.Getenv("POSTGRIP_VOLUME_REF")))
if err != nil { return err }
body := strings.NewReader("{\"disposition\":\"recreate-empty\"}")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/recovery-moves/" + encodeURIComponent(process.env.POSTGRIP_MOVE_ID ?? "") + "/volumes/" + encodeURIComponent(process.env.POSTGRIP_VOLUME_REF ?? ""));

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, },
  body: "{\"disposition\":\"recreate-empty\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/recovery-moves/' + urllib.parse.quote(os.environ['POSTGRIP_MOVE_ID'], safe='') + '/volumes/' + urllib.parse.quote(os.environ['POSTGRIP_VOLUME_REF'], safe='')
request = urllib.request.Request(endpoint, data='{"disposition":"recreate-empty"}'.encode(), method='POST')
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

- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection

[Back to Service index](./README.md)
