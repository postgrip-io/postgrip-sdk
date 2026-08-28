# Validate declarative configuration against tenant state

`POST /api/v1/services/configuration/validate` · `validatePostGripConfiguration` · Service

> Contract bundle `0375bd3bcde170bac4dbada5df6f18a588b6024ab83518c7d70e497e70c7e2c7`
> Service contract `284d54fefb7a01596003e2cc7246a619d30439ee30e14f851b7a26b164574321`

Re-canonicalizes the closed PostGrip configuration schema, verifies desiredStateDigest, and resolves tenant-dependent Worker selectors without creating a plan, stack, or managed resource.

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

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `ValidatePostGripConfigurationRequest`

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
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Successful response | `application/json` | `PostGripConfigurationValidationResult` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "canonicalConfiguration": {
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
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "issues": [
    {
      "code": "string",
      "message": "string"
    }
  ],
  "resolvedWorkers": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "name": "string",
      "path": "string",
      "version": 1
    }
  ],
  "schemaVersion": "postgrip.io/v1alpha1",
  "valid": true
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Re-canonicalizes the closed PostGrip configuration schema, verifies desiredStateDigest, and resolves tenant-dependent Worker selectors without creating a plan, stack, or managed resource.

- This read-only POST does not use Idempotency-Key.
- Local secret values are never accepted by this endpoint.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
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
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
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
  "${POSTGRIP_API_URL}/api/v1/services/configuration/validate" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration/validate")
if err != nil { return err }
body := strings.NewReader("{\"configuration\":{\"apiVersion\":\"postgrip.io/v1alpha1\",\"kind\":\"Configuration\",\"metadata\":{\"name\":\"recorded\"},\"spec\":{\"projects\":[{\"deploymentMode\":\"docker\",\"environments\":[{\"assignedWorker\":{\"id\":\"11111111-1111-4111-8111-111111111111\"},\"containerPort\":1,\"domains\":[{\"domain\":\"string\",\"isPrimary\":true,\"ref\":\"recorded\"}],\"kind\":\"production\",\"name\":\"string\",\"ref\":\"recorded\",\"variables\":[{\"isSecret\":false,\"name\":\"RECORDED_VALUE\",\"value\":\"string\"}]}],\"framework\":\"string\",\"name\":\"string\",\"projectType\":\"web\",\"ref\":\"recorded\",\"repository\":{\"connection\":\"github-app\",\"defaultBranch\":\"string\",\"provider\":\"github\",\"repoName\":\"string\",\"repoOwner\":\"string\"},\"slug\":\"recorded\"}]}},\"desiredStateDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")

client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_SERVICE_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/services/configuration/validate");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"configuration\":{\"apiVersion\":\"postgrip.io/v1alpha1\",\"kind\":\"Configuration\",\"metadata\":{\"name\":\"recorded\"},\"spec\":{\"projects\":[{\"deploymentMode\":\"docker\",\"environments\":[{\"assignedWorker\":{\"id\":\"11111111-1111-4111-8111-111111111111\"},\"containerPort\":1,\"domains\":[{\"domain\":\"string\",\"isPrimary\":true,\"ref\":\"recorded\"}],\"kind\":\"production\",\"name\":\"string\",\"ref\":\"recorded\",\"variables\":[{\"isSecret\":false,\"name\":\"RECORDED_VALUE\",\"value\":\"string\"}]}],\"framework\":\"string\",\"name\":\"string\",\"projectType\":\"web\",\"ref\":\"recorded\",\"repository\":{\"connection\":\"github-app\",\"defaultBranch\":\"string\",\"provider\":\"github\",\"repoName\":\"string\",\"repoOwner\":\"string\"},\"slug\":\"recorded\"}]}},\"desiredStateDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration/validate'
request = urllib.request.Request(endpoint, data='{"configuration":{"apiVersion":"postgrip.io/v1alpha1","kind":"Configuration","metadata":{"name":"recorded"},"spec":{"projects":[{"deploymentMode":"docker","environments":[{"assignedWorker":{"id":"11111111-1111-4111-8111-111111111111"},"containerPort":1,"domains":[{"domain":"string","isPrimary":true,"ref":"recorded"}],"kind":"production","name":"string","ref":"recorded","variables":[{"isSecret":false,"name":"RECORDED_VALUE","value":"string"}]}],"framework":"string","name":"string","projectType":"web","ref":"recorded","repository":{"connection":"github-app","defaultBranch":"string","provider":"github","repoName":"string","repoOwner":"string"},"slug":"recorded"}]}},"desiredStateDigest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

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
