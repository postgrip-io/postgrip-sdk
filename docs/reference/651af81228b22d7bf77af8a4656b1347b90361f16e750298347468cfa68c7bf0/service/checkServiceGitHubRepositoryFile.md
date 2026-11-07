# Check a GitHub repository file

`GET /api/v1/services/integrations/github/file` · `checkServiceGitHubRepositoryFile` · Service

> Contract bundle `651af81228b22d7bf77af8a4656b1347b90361f16e750298347468cfa68c7bf0`
> Service contract `37484d91ca60df1f18de9d8d4b1f8b8931e108212372a2c829e673fd83c9191b`

Checks whether a repository file exists at an optional ref through one connected GitHub account of the tenant, selected as for listServiceGitHubBranches and with the same refusals.

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
| `path` | query | yes | `string` | `"string"` | — |
| `ref` | query | no | `string` | `"string"` | — |
| `installationRef` | query | no | `string` | `"github-installation:1"` | The connected GitHub account (installation) to act through. Required only when the tenant has several active accounts and the request is not otherwise resolved to one. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `ServiceGitHubFileCheck` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "exists": true
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Checks one repository-relative path through the tenant's GitHub App installation without returning installation credentials or file contents.

- Treat owner, repository, path, and optional ref as exact caller-selected values.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_OWNER:?set POSTGRIP_OWNER to a percent-encoded query value}"
: "${POSTGRIP_REPO:?set POSTGRIP_REPO to a percent-encoded query value}"
: "${POSTGRIP_PATH:?set POSTGRIP_PATH to a percent-encoded query value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/integrations/github/file?owner=${POSTGRIP_OWNER}&repo=${POSTGRIP_REPO}&path=${POSTGRIP_PATH}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/integrations/github/file")
if err != nil { return err }
query := endpoint.Query()
query.Set("owner", os.Getenv("POSTGRIP_OWNER"))
query.Set("repo", os.Getenv("POSTGRIP_REPO"))
query.Set("path", os.Getenv("POSTGRIP_PATH"))
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
const url = new URL(baseUrl + "/api/v1/services/integrations/github/file");
url.searchParams.set('owner', process.env.POSTGRIP_OWNER ?? "");
url.searchParams.set('repo', process.env.POSTGRIP_REPO ?? "");
url.searchParams.set('path', process.env.POSTGRIP_PATH ?? "");
const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/integrations/github/file'
query = urllib.parse.urlencode({'owner': os.environ["POSTGRIP_OWNER"], 'repo': os.environ["POSTGRIP_REPO"], 'path': os.environ["POSTGRIP_PATH"]})
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

- [listServiceGitHubBranches](./listServiceGitHubBranches.md) — List GitHub Repository Branches

[Back to Service index](./README.md)
