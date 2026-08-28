# Preview a fenced multi-project release

`POST /api/v1/services/release-groups/preview` · `previewServiceReleaseGroup` · Service

> Contract bundle `cb1df40e981af36d6394cf340b6e515b84964ced7bce1cafacfbd95f0a9531a1`
> Service contract `d02f1e472705abbd18b23341b9a626051594c19e74ac11391d40c80e65421082`

Validates the complete dependency graph, exact revisions or artifacts, worker placement, current deployments, environment versions, verification policy, and overlap fences without dispatching work. Independent dependency-ready members form an explicit parallel group.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Release Groups` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:operate"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `PreviewServiceReleaseGroupRequest`

```json
{
  "failurePolicy": "compensate",
  "members": [
    {
      "branch": "main",
      "dependsOn": [],
      "environmentId": "22222222-2222-4222-8222-222222222222",
      "expectedCommitSha": "0123456789abcdef0123456789abcdef01234567",
      "key": "api",
      "projectId": "11111111-1111-4111-8111-111111111111",
      "required": true,
      "reversible": true,
      "verificationPolicy": "deployment_ready"
    },
    {
      "branch": "main",
      "dependsOn": [
        "api"
      ],
      "environmentId": "44444444-4444-4444-8444-444444444444",
      "expectedCommitSha": "abcdef0123456789abcdef0123456789abcdef01",
      "key": "frontend",
      "projectId": "33333333-3333-4333-8333-333333333333",
      "required": true,
      "reversible": true,
      "verificationPolicy": "public"
    }
  ],
  "name": "frontend-and-api",
  "successPolicy": "all_required"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Release group preview | `application/json` | `ServiceReleaseGroupPreview` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "expiresAt": "2026-01-01T00:00:00Z",
  "failurePolicy": "compensate",
  "members": [
    {
      "branch": "string",
      "dependsOn": [
        "string"
      ],
      "environmentId": "11111111-1111-4111-8111-111111111111",
      "environmentVersion": 1,
      "expectedCommitSha": "string",
      "key": "string",
      "projectId": "11111111-1111-4111-8111-111111111111",
      "projectVersion": 1,
      "required": true,
      "reversible": true,
      "verificationPolicy": "deployment_ready",
      "workerId": "11111111-1111-4111-8111-111111111111"
    }
  ],
  "name": "string",
  "previewToken": "string",
  "requestFingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "successPolicy": "all_required"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Validates the complete multi-project dependency graph and pins exact commits or immutable artifact identities, environment versions, Worker placement, current deployments, and verification policies without dispatching work.

- The signed preview expires after ten minutes and is revalidated under target locks when the release is created.
- Members without dependencies form an explicit parallel group; ordering is never inferred.

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
  "failurePolicy": "compensate",
  "members": [
    {
      "branch": "main",
      "dependsOn": [],
      "environmentId": "22222222-2222-4222-8222-222222222222",
      "expectedCommitSha": "0123456789abcdef0123456789abcdef01234567",
      "key": "api",
      "projectId": "11111111-1111-4111-8111-111111111111",
      "required": true,
      "reversible": true,
      "verificationPolicy": "deployment_ready"
    },
    {
      "branch": "main",
      "dependsOn": [
        "api"
      ],
      "environmentId": "44444444-4444-4444-8444-444444444444",
      "expectedCommitSha": "abcdef0123456789abcdef0123456789abcdef01",
      "key": "frontend",
      "projectId": "33333333-3333-4333-8333-333333333333",
      "required": true,
      "reversible": true,
      "verificationPolicy": "public"
    }
  ],
  "name": "frontend-and-api",
  "successPolicy": "all_required"
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
  "${POSTGRIP_API_URL}/api/v1/services/release-groups/preview" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/release-groups/preview")
if err != nil { return err }
body := strings.NewReader("{\"failurePolicy\":\"compensate\",\"members\":[{\"branch\":\"main\",\"dependsOn\":[],\"environmentId\":\"22222222-2222-4222-8222-222222222222\",\"expectedCommitSha\":\"0123456789abcdef0123456789abcdef01234567\",\"key\":\"api\",\"projectId\":\"11111111-1111-4111-8111-111111111111\",\"required\":true,\"reversible\":true,\"verificationPolicy\":\"deployment_ready\"},{\"branch\":\"main\",\"dependsOn\":[\"api\"],\"environmentId\":\"44444444-4444-4444-8444-444444444444\",\"expectedCommitSha\":\"abcdef0123456789abcdef0123456789abcdef01\",\"key\":\"frontend\",\"projectId\":\"33333333-3333-4333-8333-333333333333\",\"required\":true,\"reversible\":true,\"verificationPolicy\":\"public\"}],\"name\":\"frontend-and-api\",\"successPolicy\":\"all_required\"}")
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
const url = new URL(baseUrl + "/api/v1/services/release-groups/preview");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"failurePolicy\":\"compensate\",\"members\":[{\"branch\":\"main\",\"dependsOn\":[],\"environmentId\":\"22222222-2222-4222-8222-222222222222\",\"expectedCommitSha\":\"0123456789abcdef0123456789abcdef01234567\",\"key\":\"api\",\"projectId\":\"11111111-1111-4111-8111-111111111111\",\"required\":true,\"reversible\":true,\"verificationPolicy\":\"deployment_ready\"},{\"branch\":\"main\",\"dependsOn\":[\"api\"],\"environmentId\":\"44444444-4444-4444-8444-444444444444\",\"expectedCommitSha\":\"abcdef0123456789abcdef0123456789abcdef01\",\"key\":\"frontend\",\"projectId\":\"33333333-3333-4333-8333-333333333333\",\"required\":true,\"reversible\":true,\"verificationPolicy\":\"public\"}],\"name\":\"frontend-and-api\",\"successPolicy\":\"all_required\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/release-groups/preview'
request = urllib.request.Request(endpoint, data='{"failurePolicy":"compensate","members":[{"branch":"main","dependsOn":[],"environmentId":"22222222-2222-4222-8222-222222222222","expectedCommitSha":"0123456789abcdef0123456789abcdef01234567","key":"api","projectId":"11111111-1111-4111-8111-111111111111","required":true,"reversible":true,"verificationPolicy":"deployment_ready"},{"branch":"main","dependsOn":["api"],"environmentId":"44444444-4444-4444-8444-444444444444","expectedCommitSha":"abcdef0123456789abcdef0123456789abcdef01","key":"frontend","projectId":"33333333-3333-4333-8333-333333333333","required":true,"reversible":true,"verificationPolicy":"public"}],"name":"frontend-and-api","successPolicy":"all_required"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [cancelServiceReleaseGroup](./cancelServiceReleaseGroup.md) — Cancel and compensate a release group
- [createServiceReleaseGroup](./createServiceReleaseGroup.md) — Create a fenced multi-project release saga
- [getServiceReleaseGroup](./getServiceReleaseGroup.md) — Get aggregate and per-member release state
- [listServiceReleaseGroupEvents](./listServiceReleaseGroupEvents.md) — List bounded release audit events
- [listServiceReleaseGroups](./listServiceReleaseGroups.md) — List release groups
- [retryServiceReleaseGroup](./retryServiceReleaseGroup.md) — Retry a safely recovered release group

[Back to Service index](./README.md)
