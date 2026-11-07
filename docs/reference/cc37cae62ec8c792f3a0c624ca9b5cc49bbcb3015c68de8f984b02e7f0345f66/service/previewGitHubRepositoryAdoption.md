# Preview GitHub App repository adoption

`POST /api/v1/services/project/{serviceId}/repository/github/adoption-preview` · `previewGitHubRepositoryAdoption` · Service

> Contract bundle `cc37cae62ec8c792f3a0c624ca9b5cc49bbcb3015c68de8f984b02e7f0345f66`
> Service contract `1a03ed98a794cbce8a45d413e51db982d7b72dc1b4dcaf71452b553fbea9b16a`

Records an expiring adoption preview against exactly one GitHub account of the tenant. The account is installationRef when given, else the one active account whose login owns an owner/name repository, else the tenant's only account; a repositoryId selection carries no owner, so a tenant with several accounts names the account with installationRef. Refusals: 400 GITHUB_INSTALLATION_SELECTOR_REQUIRED (several accounts and the request resolves none), 400 INVALID_INSTALLATION_REF, and 409 GITHUB_INSTALLATION_REQUIRED (installationRef is not an active account of the tenant). GitHub repository adoption is enabled per organization: where it is not, the operation answers `404` `CAPABILITY_NOT_ENABLED`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:read"]]` |
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `serviceId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `GitHubRepositoryAdoptionPreviewRequest`

```json
{
  "automaticDeployments": true,
  "repositoryId": 1
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Immutable, expiring adoption preview | `application/json` | `GitHubRepositoryAdoptionPreview` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "automaticDeployments": true,
  "changes": [
    "string"
  ],
  "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expiresAt": "2026-01-01T00:00:00Z",
  "id": "11111111-1111-4111-8111-111111111111",
  "missingPermissions": [
    "string"
  ],
  "projectId": "11111111-1111-4111-8111-111111111111",
  "receipt": {
    "auditRecorded": true,
    "replayed": true,
    "requestId": "string"
  },
  "repository": {
    "adoptionState": "available",
    "defaultBranch": "string",
    "fullName": "string",
    "id": 1,
    "installationRef": "github-installation:1",
    "missingPermissions": [
      "string"
    ],
    "name": "string",
    "owner": "string",
    "permissions": {
      "contents": "string"
    },
    "private": true
  },
  "repositoryEtag": "string",
  "requiredPermissions": [
    "string"
  ],
  "state": "ready",
  "targetWorkerIds": [
    "11111111-1111-4111-8111-111111111111"
  ],
  "webhookChange": "disable"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Resolves an exact repository ID or owner/name through the tenant GitHub App installation and records a short-lived, secret-free preview of permissions, Worker targets, webhook changes, and the repository ETag.

- Idempotency: required.
- Execute the preview before its expiry and recreate it after any repository, permission, installation, or Worker-assignment change.

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
  "automaticDeployments": true,
  "repositoryId": 1
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
  "${POSTGRIP_API_URL}/api/v1/services/project/${POSTGRIP_SERVICE_ID}/repository/github/adoption-preview" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/project/" + url.PathEscape(os.Getenv("POSTGRIP_SERVICE_ID")) + "/repository/github/adoption-preview")
if err != nil { return err }
body := strings.NewReader("{\"automaticDeployments\":true,\"repositoryId\":1}")
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
const url = new URL(baseUrl + "/api/v1/services/project/" + encodeURIComponent(process.env.POSTGRIP_SERVICE_ID ?? "") + "/repository/github/adoption-preview");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"automaticDeployments\":true,\"repositoryId\":1}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/project/' + urllib.parse.quote(os.environ['POSTGRIP_SERVICE_ID'], safe='') + '/repository/github/adoption-preview'
request = urllib.request.Request(endpoint, data='{"automaticDeployments":true,"repositoryId":1}'.encode(), method='POST')
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
