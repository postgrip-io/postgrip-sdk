# Create a deterministic declarative configuration plan

`POST /api/v1/services/configuration-stacks/{stackKey}/plans` · `createPostGripConfigurationPlan` · Service

> Contract bundle `5be292e94aaa518d4cc4fc97d7309dfbcbf16e6139da32908c130b04708884b6`
> Service contract `afad86eba107c2175f3af8dbf50bd4f58c4732ac291126e8df5d07680b731505`

Validates canonical desired state and current tenant references, then creates an immutable, expiring read-only plan. The request requires Idempotency-Key. It never creates a configuration stack or mutates a managed Service resource, and its response contains secret input names and versions but never resolved secret values.

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
| Idempotency | `required` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `stackKey` | path | yes | `string` | `"recorded"` | — |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `CreatePostGripConfigurationPlanRequest`

```json
{
  "allowAdoption": true,
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
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prune": true
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Plan created | `application/json` | `PostGripConfigurationPlan` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "allowAdoption": true,
  "baseStackRevision": 1,
  "createdAt": "2026-01-01T00:00:00Z",
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expiresAt": "2026-01-01T00:00:00Z",
  "id": "11111111-1111-4111-8111-111111111111",
  "planDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prune": true,
  "schemaVersion": "string",
  "stackKey": "string",
  "state": "ready",
  "summary": {
    "adopt": 1,
    "blocked": 1,
    "create": 1,
    "delete": 1,
    "noOp": 1,
    "reconcileGitHub": 1,
    "reconcileSecret": 1,
    "replace": 1,
    "total": 1,
    "update": 1
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Validates canonical desired state and current tenant references, then creates an immutable, expiring read-only plan. The request requires Idempotency-Key. It never creates a configuration stack or mutates a managed Service resource, and its response contains secret input names and versions but never resolved secret values.

- Idempotency: required.
- Plans expire after 30 minutes by default and no later than 24 hours.
- Use the paginated action operation to inspect the complete safe action graph.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_STACK_KEY:?set POSTGRIP_STACK_KEY to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "allowAdoption": true,
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
  "desiredStateDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "prune": true
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
  "${POSTGRIP_API_URL}/api/v1/services/configuration-stacks/${POSTGRIP_STACK_KEY}/plans" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/configuration-stacks/" + url.PathEscape(os.Getenv("POSTGRIP_STACK_KEY")) + "/plans")
if err != nil { return err }
body := strings.NewReader("{\"allowAdoption\":true,\"configuration\":{\"apiVersion\":\"postgrip.io/v1alpha1\",\"kind\":\"Configuration\",\"metadata\":{\"name\":\"recorded\"},\"spec\":{\"projects\":[{\"deploymentMode\":\"docker\",\"environments\":[{\"assignedWorker\":{\"id\":\"11111111-1111-4111-8111-111111111111\"},\"containerPort\":1,\"domains\":[{\"domain\":\"string\",\"isPrimary\":true,\"ref\":\"recorded\"}],\"kind\":\"production\",\"name\":\"string\",\"ref\":\"recorded\",\"variables\":[{\"isSecret\":false,\"name\":\"RECORDED_VALUE\",\"value\":\"string\"}]}],\"framework\":\"string\",\"name\":\"string\",\"projectType\":\"web\",\"ref\":\"recorded\",\"repository\":{\"connection\":\"github-app\",\"defaultBranch\":\"string\",\"provider\":\"github\",\"repoName\":\"string\",\"repoOwner\":\"string\"},\"slug\":\"recorded\"}]}},\"desiredStateDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"prune\":true}")
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
const url = new URL(baseUrl + "/api/v1/services/configuration-stacks/" + encodeURIComponent(process.env.POSTGRIP_STACK_KEY ?? "") + "/plans");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"allowAdoption\":true,\"configuration\":{\"apiVersion\":\"postgrip.io/v1alpha1\",\"kind\":\"Configuration\",\"metadata\":{\"name\":\"recorded\"},\"spec\":{\"projects\":[{\"deploymentMode\":\"docker\",\"environments\":[{\"assignedWorker\":{\"id\":\"11111111-1111-4111-8111-111111111111\"},\"containerPort\":1,\"domains\":[{\"domain\":\"string\",\"isPrimary\":true,\"ref\":\"recorded\"}],\"kind\":\"production\",\"name\":\"string\",\"ref\":\"recorded\",\"variables\":[{\"isSecret\":false,\"name\":\"RECORDED_VALUE\",\"value\":\"string\"}]}],\"framework\":\"string\",\"name\":\"string\",\"projectType\":\"web\",\"ref\":\"recorded\",\"repository\":{\"connection\":\"github-app\",\"defaultBranch\":\"string\",\"provider\":\"github\",\"repoName\":\"string\",\"repoOwner\":\"string\"},\"slug\":\"recorded\"}]}},\"desiredStateDigest\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"prune\":true}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/configuration-stacks/' + urllib.parse.quote(os.environ['POSTGRIP_STACK_KEY'], safe='') + '/plans'
request = urllib.request.Request(endpoint, data='{"allowAdoption":true,"configuration":{"apiVersion":"postgrip.io/v1alpha1","kind":"Configuration","metadata":{"name":"recorded"},"spec":{"projects":[{"deploymentMode":"docker","environments":[{"assignedWorker":{"id":"11111111-1111-4111-8111-111111111111"},"containerPort":1,"domains":[{"domain":"string","isPrimary":true,"ref":"recorded"}],"kind":"production","name":"string","ref":"recorded","variables":[{"isSecret":false,"name":"RECORDED_VALUE","value":"string"}]}],"framework":"string","name":"string","projectType":"web","ref":"recorded","repository":{"connection":"github-app","defaultBranch":"string","provider":"github","repoName":"string","repoOwner":"string"},"slug":"recorded"}]}},"desiredStateDigest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","prune":true}'.encode(), method='POST')
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
