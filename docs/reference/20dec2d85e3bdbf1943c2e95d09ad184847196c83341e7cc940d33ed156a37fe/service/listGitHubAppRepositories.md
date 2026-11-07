# List repositories authorized for GitHub App adoption

`GET /api/v1/services/integrations/github/repositories` · `listGitHubAppRepositories` · Service

> Contract bundle `20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`
> Service contract `37484d91ca60df1f18de9d8d4b1f8b8931e108212372a2c829e673fd83c9191b`

Lists repositories visible through one connected GitHub account (installation) of the tenant. Pass installationRef when the tenant has several active accounts; a tenant with one account needs no selector, and a cursor alone continues the installation it was issued for. Refusals: 400 GITHUB_INSTALLATION_SELECTOR_REQUIRED (several accounts and no installationRef or cursor), 400 INVALID_INSTALLATION_REF, 400 INVALID_CURSOR (malformed, another tenant, or issued for an installation other than installationRef), 410 CURSOR_EXPIRED (24 hours), and 409 GITHUB_INSTALLATION_REQUIRED (the selected installation is not an active account of the tenant, including a disconnected or revoked one). There is no cursor across accounts. GitHub repository adoption is enabled per organization: where it is not, the operation answers `404` `CAPABILITY_NOT_ENABLED`.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Administration` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `limit` | query | no | `integer` | `1` | — |
| `cursor` | query | no | `string` | `"string"` | — |
| `installationRef` | query | no | `string` | `"github-installation:1"` | The connected GitHub account (installation) to act through. Required only when the tenant has several active accounts and the request is not otherwise resolved to one. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Bounded repositories visible through the tenant GitHub App installation | `application/json` | `GitHubRepositoryList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
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
    }
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns one bounded cursor page of repositories visible through the tenant-owned GitHub App installation, including only safe identity, permission, and adoption metadata.

- Follow nextCursor until it is empty; do not manufacture or reuse a cursor across tenants or installation changes.
- Repository names are audited tenant metadata.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/integrations/github/repositories" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/integrations/github/repositories")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "GET", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))


client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/integrations/github/repositories");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/integrations/github/repositories'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


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
