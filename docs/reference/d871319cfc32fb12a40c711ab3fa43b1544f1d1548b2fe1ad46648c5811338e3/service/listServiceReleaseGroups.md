# List coordinated release groups

`GET /api/v1/services/release-groups` · `listServiceReleaseGroups` · Service

> Contract bundle `d871319cfc32fb12a40c711ab3fa43b1544f1d1548b2fe1ad46648c5811338e3`
> Service contract `bfcc999223f092746a422fdad8c98df14fcb1af76add477fb059e35d583945e5`

Returns bounded opaque-cursor pages of aggregate release state together with exact per-member deployment, verification, compensation, and safe-error projections.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Release Groups` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token` |
| Required scopes | `[["services:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `limit` | query | no | `integer` | `1` | — |
| `cursor` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Release groups | `application/json` | `ServiceReleaseGroupList` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "createdAt": "2026-01-01T00:00:00Z",
      "failurePolicy": "compensate",
      "id": "11111111-1111-4111-8111-111111111111",
      "members": [
        {
          "attempt": 1,
          "branch": "string",
          "createdAt": "2026-01-01T00:00:00Z",
          "dependsOn": [
            "string"
          ],
          "environmentId": "11111111-1111-4111-8111-111111111111",
          "expectedCommitSha": "string",
          "expectedEnvironmentVersion": 1,
          "id": "11111111-1111-4111-8111-111111111111",
          "key": "string",
          "projectId": "11111111-1111-4111-8111-111111111111",
          "required": true,
          "reversible": true,
          "state": "pending",
          "updatedAt": "2026-01-01T00:00:00Z",
          "verificationAttempts": 1,
          "verificationPolicy": "deployment_ready",
          "workerId": "11111111-1111-4111-8111-111111111111"
        },
        {
          "attempt": 1,
          "branch": "string",
          "createdAt": "2026-01-01T00:00:00Z",
          "dependsOn": [
            "string"
          ],
          "environmentId": "11111111-1111-4111-8111-111111111111",
          "expectedCommitSha": "string",
          "expectedEnvironmentVersion": 1,
          "id": "11111111-1111-4111-8111-111111111111",
          "key": "string",
          "projectId": "11111111-1111-4111-8111-111111111111",
          "required": true,
          "reversible": true,
          "state": "pending",
          "updatedAt": "2026-01-01T00:00:00Z",
          "verificationAttempts": 1,
          "verificationPolicy": "deployment_ready",
          "workerId": "11111111-1111-4111-8111-111111111111"
        }
      ],
      "name": "string",
      "requestFingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "retryCount": 1,
      "state": "pending",
      "successPolicy": "all_required",
      "updatedAt": "2026-01-01T00:00:00Z"
    }
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns bounded opaque-cursor pages of aggregate release state together with exact per-member deployment, verification, compensation, and safe-error projections.

- Treat cursors as opaque and stop when nextCursor is empty.

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
  "${POSTGRIP_API_URL}/api/v1/services/release-groups" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/release-groups")
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
const url = new URL(baseUrl + "/api/v1/services/release-groups");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/release-groups'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


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
- [previewServiceReleaseGroup](./previewServiceReleaseGroup.md) — Preview and fence a multi-project release
- [retryServiceReleaseGroup](./retryServiceReleaseGroup.md) — Retry a safely recovered release group

[Back to Service index](./README.md)
