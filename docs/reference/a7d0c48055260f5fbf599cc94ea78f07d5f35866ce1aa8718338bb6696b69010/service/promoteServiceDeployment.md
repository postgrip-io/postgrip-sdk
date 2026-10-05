# Promote Service Deployment

`POST /api/v1/services/project/{serviceId}/promotions` · `promoteServiceDeployment` · Service

> Contract bundle `a7d0c48055260f5fbf599cc94ea78f07d5f35866ce1aa8718338bb6696b69010`
> Service contract `6f232ea94805a973c407e441b0ac334bb1b3916f9ca72c732dbee3a0b764513e`

Promotes a source deployment's revision to a target environment. A private GitHub service deploys with the repository credential supplied to the target Worker when that Worker holds one. A deployment never mints an installation token over a supplied credential, including for a service adopted from a GitHub installation; only adoption or rebinding the service moves it back to its installation. The request fails with `409` and queues nothing when the supplied credential cannot be used: `SECRET_RESUBMISSION_REQUIRED` when it awaits resubmission or a re-send of it failed, and `REPOSITORY_CREDENTIAL_DELIVERY_PENDING` with `Retry-After` while it is still being delivered, whether the service is bound to no GitHub installation, adopted from one, or bound to one from the console. For a private GitHub service bound to no GitHub installation, `REPOSITORY_CREDENTIAL_UNAVAILABLE` means the target Worker holds no supplied credential. None of these three refusals consumes the Idempotency-Key: resubmit or supply the credential with putServiceRepositoryCredential (`source-access`), bind the service, or wait for the delivery, then retry the request, with the same key if you like.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:operate"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `PromoteServiceDeploymentRequest`

```json
{
  "expectedArtifactIdentity": "string",
  "expectedCommitSha": "string",
  "expectedTargetWorkerId": "11111111-1111-4111-8111-111111111111",
  "previewToken": "string",
  "sourceDeploymentId": "11111111-1111-4111-8111-111111111111",
  "targetEnvironmentId": "11111111-1111-4111-8111-111111111111"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Successful response | `application/json` | `DeploymentOperationResponse` |
| `409` | Conflict. Four refusals queue nothing and are not stored against the Idempotency-Key, so a retry with the same key runs the request again: `SECRET_RESUBMISSION_REQUIRED`, the target Worker's supplied repository credential awaits resubmission or a re-send of it failed (resubmit it with putServiceRepositoryCredential, `source-access`); `REPOSITORY_CREDENTIAL_DELIVERY_PENDING`, the Worker's supplied credential is still being delivered (retry after `Retry-After` seconds); `REPOSITORY_CREDENTIAL_UNAVAILABLE`, the service is bound to no GitHub installation and the target Worker holds no supplied credential (supply one with putServiceRepositoryCredential, `source-access`, or bind the service); `WRITE_OUTCOME_UNKNOWN`, a LadybugDB service's starter Compose file write reached the target Worker and its answer was lost, so the file may or may not have been written, and nothing was deployed (a retry rereads the file before it deploys). Other conflicts on this route, such as `SERVICE_STATE_CHANGED`, `IDEMPOTENCY_CONFLICT` and `IDEMPOTENCY_IN_PROGRESS`, also use this status. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "deployment": {
    "aliases": [
      "https://www.example.com/"
    ],
    "branch": "string",
    "commitSha": "string",
    "createdAt": "2026-01-01T00:00:00Z",
    "cutoverState": "candidate",
    "environmentId": "11111111-1111-4111-8111-111111111111",
    "id": "11111111-1111-4111-8111-111111111111",
    "isCurrent": true,
    "projectId": "11111111-1111-4111-8111-111111111111",
    "status": "string",
    "triggerKind": "string",
    "updatedAt": "2026-01-01T00:00:00Z"
  },
  "deploymentId": "11111111-1111-4111-8111-111111111111",
  "environmentId": "11111111-1111-4111-8111-111111111111",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "serviceRef": "string",
  "status": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined POST /api/v1/services/project/{serviceId}/promotions behavior.

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
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "expectedArtifactIdentity": "string",
  "expectedCommitSha": "string",
  "expectedTargetWorkerId": "11111111-1111-4111-8111-111111111111",
  "previewToken": "string",
  "sourceDeploymentId": "11111111-1111-4111-8111-111111111111",
  "targetEnvironmentId": "11111111-1111-4111-8111-111111111111"
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/promotions" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/promotions")
if err != nil { return err }
body := strings.NewReader("{\"expectedArtifactIdentity\":\"string\",\"expectedCommitSha\":\"string\",\"expectedTargetWorkerId\":\"11111111-1111-4111-8111-111111111111\",\"previewToken\":\"string\",\"sourceDeploymentId\":\"11111111-1111-4111-8111-111111111111\",\"targetEnvironmentId\":\"11111111-1111-4111-8111-111111111111\"}")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/promotions");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"expectedArtifactIdentity\":\"string\",\"expectedCommitSha\":\"string\",\"expectedTargetWorkerId\":\"11111111-1111-4111-8111-111111111111\",\"previewToken\":\"string\",\"sourceDeploymentId\":\"11111111-1111-4111-8111-111111111111\",\"targetEnvironmentId\":\"11111111-1111-4111-8111-111111111111\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/promotions'
request = urllib.request.Request(endpoint, data='{"expectedArtifactIdentity":"string","expectedCommitSha":"string","expectedTargetWorkerId":"11111111-1111-4111-8111-111111111111","previewToken":"string","sourceDeploymentId":"11111111-1111-4111-8111-111111111111","targetEnvironmentId":"11111111-1111-4111-8111-111111111111"}'.encode(), method='POST')
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
- [applyPostGripConfigurationPlan](./applyPostGripConfigurationPlan.md) — Apply PostGrip Configuration Plan
- [applyServiceVariables](./applyServiceVariables.md) — Apply Service Variables
- [attachTargetService](./attachTargetService.md) — Attach Target Service
- [bindServiceVolume](./bindServiceVolume.md) — Bind Service Volume
- [clearServiceRepositoryCredential](./clearServiceRepositoryCredential.md) — Clear Service Repository Credential
- [clearServiceVariableValue](./clearServiceVariableValue.md) — Clear Service Variable Value
- [clearTargetServiceConnection](./clearTargetServiceConnection.md) — Clear Target Service Connection

[Back to Service index](./README.md)
