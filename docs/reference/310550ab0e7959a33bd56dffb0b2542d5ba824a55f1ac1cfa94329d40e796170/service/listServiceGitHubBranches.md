# List GitHub repository branches

`GET /api/v1/services/integrations/github/branches` · `listServiceGitHubBranches` · Service

> Contract bundle `310550ab0e7959a33bd56dffb0b2542d5ba824a55f1ac1cfa94329d40e796170`
> Service contract `b5177fdfd9a35d163f37c79aa8cdf51fada33ec02d6a50db5452064107aaf6cf`

Lists branches through one connected GitHub account of the tenant without exposing installation credentials. The account is installationRef when given, else the one active account whose login is owner, else the tenant's only account. Refusals: 400 GITHUB_INSTALLATION_SELECTOR_REQUIRED, 400 INVALID_INSTALLATION_REF, 400 GITHUB_NOT_CONNECTED (no account), 409 GITHUB_INSTALLATION_REQUIRED (installationRef is not an active account), and 422 GITHUB_REPOSITORY_NOT_VISIBLE.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Repositories` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:config:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `owner` | query | yes | `string` | `"string"` | — |
| `repo` | query | yes | `string` | `"string"` | — |
| `installationRef` | query | no | `string` | `"github-installation:1"` | The connected GitHub account (installation) to act through. Required only when the tenant has several active accounts and the request is not otherwise resolved to one. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `array<ServiceGitHubBranch>` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
    "name": "string"
  }
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Lists branches visible through the tenant's GitHub App installation without exposing installation credentials.

- Use an exact repository owner and name; branch names are untrusted display data.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_OWNER:?set POSTGRIP_OWNER to a percent-encoded query value}"
: "${POSTGRIP_REPO:?set POSTGRIP_REPO to a percent-encoded query value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/integrations/github/branches?owner=${POSTGRIP_OWNER}&repo=${POSTGRIP_REPO}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/integrations/github/branches")
if err != nil { return err }
query := endpoint.Query()
query.Set("owner", os.Getenv("POSTGRIP_OWNER"))
query.Set("repo", os.Getenv("POSTGRIP_REPO"))
endpoint.RawQuery = query.Encode()
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
const url = new URL(baseUrl + "/api/v1/services/integrations/github/branches");
url.searchParams.set('owner', process.env.POSTGRIP_OWNER ?? "");
url.searchParams.set('repo', process.env.POSTGRIP_REPO ?? "");
const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/integrations/github/branches'
query = urllib.parse.urlencode({'owner': os.environ["POSTGRIP_OWNER"], 'repo': os.environ["POSTGRIP_REPO"]})
endpoint += '?' + query
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [checkServiceGitHubRepositoryFile](./checkServiceGitHubRepositoryFile.md) — Check GitHub Repository File

[Back to Service index](./README.md)
