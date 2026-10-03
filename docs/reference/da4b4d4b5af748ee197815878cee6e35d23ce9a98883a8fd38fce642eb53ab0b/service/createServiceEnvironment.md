# Create Service Environment

`POST /api/v1/services/project/{serviceId}/environments` · `createServiceEnvironment` · Service

> Contract bundle `da4b4d4b5af748ee197815878cee6e35d23ce9a98883a8fd38fce642eb53ab0b`
> Service contract `b4afb1f8fb933715606c1edbcb1853c71fda7a95b90e6c08814eb96e306fe33a`

Uses the contract-defined POST /api/v1/services/project/{serviceId}/environments behavior.

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
| `If-Match` | header | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `CreateServiceEnvironmentRequest`

```json
{
  "kind": "string",
  "name": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Successful response | `application/json` | `ServiceEnvironmentMutationResponse` |
| `409` | Conflict. `WORKER_REVOKED` (`details.workerId`): with `assignedWorkerId`, that Worker is revoked; revoked is terminal (enroll a new Worker or replace the revoked one), so the refusal is stored against the Idempotency-Key and replays. Without `assignedWorkerId`, the Worker selection chose (the project default or automatic placement) was revoked before the placement locked it; that refusal is not stored against the key, so a retry with the same key selects again. `NO_ELIGIBLE_WORKER` (`details.requiredCapabilities`, `details.defaultWorkerId`): no Worker is eligible, or the Worker placement chose was removed, replaced or became ineligible after the request's pre-check, including a removed or replaced project default. Placement does not reselect, but the refusal is not stored against the key, so a retry with the same key selects again. `WORKER_UPGRADE_REQUIRED`: with `assignedWorkerId`, that Worker does not advertise a capability the operation needs (`details.workerId`, `details.requiredCapability`); without it, the project default or automatic candidate runs a version below the one the control plane expects (`details.requiredCapabilities`). Upgrade the Worker and retry; the refusal is not stored against the key, so a retry with the same key runs again. `404` `NOT_FOUND` applies only to an explicit `assignedWorkerId` already removed or replaced when the request arrived, including one that is also revoked. Other conflicts on this route also use this status. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "configurationRevision": 1,
  "effect": "string",
  "environment": {
    "buildCommand": "string",
    "createdAt": "2026-01-01T00:00:00Z",
    "etag": "string",
    "id": "11111111-1111-4111-8111-111111111111",
    "kind": "string",
    "name": "string",
    "outputDir": "string",
    "previewBrowserCheckEnabled": true,
    "previewPathSegment": "string",
    "projectId": "11111111-1111-4111-8111-111111111111",
    "updatedAt": "2026-01-01T00:00:00Z",
    "version": 1,
    "volumeBindings": [
      {
        "containerPath": "string",
        "etag": "string",
        "readOnly": true,
        "version": 1,
        "volumeRef": "11111111-1111-4111-8111-111111111111"
      }
    ],
    "volumes": [
      {
        "containerPath": "/data"
      }
    ]
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

Uses the contract-defined POST /api/v1/services/project/{serviceId}/environments behavior.

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
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
: "${POSTGRIP_IF_MATCH:?set POSTGRIP_IF_MATCH for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "kind": "string",
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
  POST \
  --header \
  "Content-Type: application/json" \
  --data-binary \
  "@${POSTGRIP_BODY_FILE}" \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  --header \
  "If-Match: ${POSTGRIP_IF_MATCH}" \
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/environments" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/environments")
if err != nil { return err }
body := strings.NewReader("{\"kind\":\"string\",\"name\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/environments");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, "If-Match": process.env.POSTGRIP_IF_MATCH, },
  body: "{\"kind\":\"string\",\"name\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/environments'
request = urllib.request.Request(endpoint, data='{"kind":"string","name":"string"}'.encode(), method='POST')
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
