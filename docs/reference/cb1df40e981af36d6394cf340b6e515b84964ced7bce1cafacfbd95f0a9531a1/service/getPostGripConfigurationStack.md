# Get declarative configuration stack state

`GET /api/v1/services/configuration-stacks/{stackKey}` · `getPostGripConfigurationStack` · Service

> Contract bundle `cb1df40e981af36d6394cf340b6e515b84964ced7bce1cafacfbd95f0a9531a1`
> Service contract `d02f1e472705abbd18b23341b9a626051594c19e74ac11391d40c80e65421082`

Returns the last successfully applied safe desired state, ownership ledger, secret input names and versions, and stack revision. A stack is absent until the first authorized apply; planning alone never creates it.

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
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `stackKey` | path | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `PostGripConfigurationStack` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "configuration": {
    "apiVersion": "postgrip.io/v1alpha1",
    "kind": "Configuration",
    "metadata": {
      "name": "recorded"
    },
    "spec": {
      "projects": [
        {
          "deploymentMode": "docker",
          "environments": [
            {
              "assignedWorker": {
                "id": "11111111-1111-4111-8111-111111111111"
              },
              "containerPort": 1,
              "domains": [
                {
                  "domain": "string",
                  "isPrimary": true,
                  "ref": "recorded"
                }
              ],
              "kind": "production",
              "name": "string",
              "ref": "recorded",
              "variables": [
                {
                  "isSecret": false,
                  "name": "RECORDED_VALUE",
                  "value": "string"
                }
              ]
            }
          ],
          "framework": "string",
          "name": "string",
          "projectType": "web",
          "ref": "recorded",
          "repository": {
            "connection": "github-app",
            "defaultBranch": "string",
            "provider": "github",
            "repoName": "string",
            "repoOwner": "string"
          },
          "slug": "recorded"
        }
      ]
    }
  },
  "createdAt": "2026-01-01T00:00:00Z",
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "id": "11111111-1111-4111-8111-111111111111",
  "key": "string",
  "resources": [
    {
      "etag": "string",
      "path": "string",
      "resourceId": "11111111-1111-4111-8111-111111111111",
      "resourceType": "string"
    }
  ],
  "revision": 1,
  "schemaVersion": "string",
  "secretVersions": [
    {
      "inputName": "string",
      "path": "string",
      "secretVersion": "string"
    }
  ],
  "updatedAt": "2026-01-01T00:00:00Z"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns the last successfully applied safe desired state, ownership ledger, secret input names and versions, and stack revision. A stack is absent until the first authorized apply; planning alone never creates it.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_STACK_KEY:?set POSTGRIP_STACK_KEY to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/configuration-stacks/${POSTGRIP_STACK_KEY}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration-stacks/" + url.PathEscape(os.Getenv("POSTGRIP_STACK_KEY")))
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
const url = new URL(baseUrl + "/api/v1/services/configuration-stacks/" + encodeURIComponent(process.env.POSTGRIP_STACK_KEY ?? ""));

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration-stacks/' + urllib.parse.quote(os.environ['POSTGRIP_STACK_KEY'], safe='')
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
