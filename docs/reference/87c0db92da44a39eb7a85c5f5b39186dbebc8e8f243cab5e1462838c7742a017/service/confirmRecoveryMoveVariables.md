# Confirm Recovery Move Variables

`POST /api/v1/services/project/{serviceId}/environments/{environmentId}/recovery-moves/{moveId}/variables/confirm` · `confirmRecoveryMoveVariables` · Service

> Contract bundle `87c0db92da44a39eb7a85c5f5b39186dbebc8e8f243cab5e1462838c7742a017`
> Service contract `a04e230c8143ee3f8e3ed9ff0689e45a02efaab69e07f4f3bf41fd1719f4b231`

Confirms that the variables the environment's Worker now holds are the complete set, after a recovery move off a lost Worker. Variable values lived only on the lost source, so the move restores none: it records the variables the control plane knows of (the record's `variables.knownVariables`), creates each `resubmissionRequired` one on the destination with an empty value, and refuses every deployment of the environment as `409 VARIABLES_UNRECONCILED` until this confirmation. Supply every value on the environment's Worker first (through the Service API or the console); any other variable the environment needs must be created too, since the known inventory may be incomplete. `If-Match` is the variable collection ETag of the Worker the environment is on (the move's destination, or the Worker a later live reassignment relayed the set to), read from its masked variable collection, so you confirm exactly the set you read. In one transaction it clears the environment's mark, marks the record's variables `confirmed` and advances the record's version, and it is audited with every confirmed variable name. Refusals write nothing.

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
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceRecoveryMoveConfirmationResponse` |
| `409` | Conflict. `VARIABLE_RESUBMISSION_REQUIRED`: a recorded `resubmissionRequired` variable that still exists in the Service API is absent from the environment's Worker or has no value there (`details.names`); supply them, or delete a variable the environment no longer needs through the Service API. `SERVICE_STATE_CHANGED`: the record's variables are not awaiting confirmation (already confirmed, recorded before variable reconciliation, or superseded by a later recovery move of the environment), the environment has no Worker, or it moved to another Worker while its variables were read. `WORKER_UPGRADE_REQUIRED`: the environment's Worker cannot serve its masked variables. `VARIABLE_RESUBMISSION_REQUIRED`, `WORKER_UPGRADE_REQUIRED` and the Worker changes of `SERVICE_STATE_CHANGED` are not stored against the Idempotency-Key, so a retry with the same key runs again. Other conflicts on this route also use this status. | `application/json` | `ErrorResponse` |
| `412` | `PRECONDITION_FAILED`: `If-Match` is not the current variable collection ETag of the environment's Worker. Read the variables again before confirming. Not stored against the Idempotency-Key. | `application/json` | `ErrorResponse` |
| `503` | `WORKER_UNAVAILABLE`: the environment's Worker could not be read. Not stored against the Idempotency-Key; retry once it is reachable. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "confirmedVariableNames": [
    "string"
  ],
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

Confirms that the variables the environment's Worker now holds are the complete set after a recovery move off a lost Worker, fenced by If-Match on that Worker's variable collection ETag. Until then every deployment of the environment is refused as VARIABLES_UNRECONCILED. It clears the environment's mark, marks the record's variables confirmed and advances the record's version in one transaction; a recorded resubmissionRequired variable that is absent or has no value is refused as VARIABLE_RESUBMISSION_REQUIRED and nothing is written.

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
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
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
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments/${POSTGRIP_ENVIRONMENT_ID}/recovery-moves/${POSTGRIP_MOVE_ID}/variables/confirm" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments/" + url.PathEscape(os.Getenv("POSTGRIP_ENVIRONMENT_ID")) + "/recovery-moves/" + url.PathEscape(os.Getenv("POSTGRIP_MOVE_ID")) + "/variables/confirm")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
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
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments/" + encodeURIComponent(process.env.POSTGRIP_ENVIRONMENT_ID ?? "") + "/recovery-moves/" + encodeURIComponent(process.env.POSTGRIP_MOVE_ID ?? "") + "/variables/confirm");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments/' + urllib.parse.quote(os.environ['POSTGRIP_ENVIRONMENT_ID'], safe='') + '/recovery-moves/' + urllib.parse.quote(os.environ['POSTGRIP_MOVE_ID'], safe='') + '/variables/confirm'
request = urllib.request.Request(endpoint, method='POST')
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

- [adoptGitHubRepository](./adoptGitHubRepository.md) — Adopt GitHub Repository
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection

[Back to Service index](./README.md)
