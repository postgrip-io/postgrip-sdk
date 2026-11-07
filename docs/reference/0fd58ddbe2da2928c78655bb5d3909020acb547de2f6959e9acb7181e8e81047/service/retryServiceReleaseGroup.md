# Retry a safely recovered release group

`POST /api/v1/services/release-groups/{releaseGroupId}/retry` · `retryServiceReleaseGroup` · Service

> Contract bundle `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`
> Service contract `dd9e4b81913e3757c83c6806500d5bc831f1bd379ca28210c5311f2c79a280bd`

Retries the same pinned revisions only after compensation or cancellation reached a safe terminal state. Intervention-required groups require a new preview.

## Operation

| Field | Value |
| --- | --- |
| Plane | `service` |
| Resource tags | `Release Groups` |
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
| `releaseGroupId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | Durable multi-project release saga identifier. |
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Retry accepted | `application/json` | `ServiceReleaseGroup` |
| `404` | Not found. `RELEASE_GROUP_NOT_FOUND`: no release group with that id exists in your organization, or the id is not a UUID. | `application/json` | `ErrorResponse` |
| `409` | Conflict. `RETRY_NOT_ALLOWED`: the release group is not `recovered` or `cancelled`; an intervention-required group needs a new preview. `RETRY_LIMIT_REACHED`: the group was already retried 20 times. `SERVICE_STATE_CHANGED`: a member's target changed after recovery, so the pinned plan no longer applies; create a new preview. `details.memberKey` and `details.memberId` name the first such member, and `details.reason` says what changed: `projectVersion` (the service's configuration changed), `environmentVersion` (the environment changed or was removed), `worker` (the environment moved to another Worker) or `currentDeployment` (another deployment became current). Other conflicts on this route also use this status. | `application/json` | `ErrorResponse` |
| `503` | Unavailable. `AUDIT_UNAVAILABLE`: the request could not be recorded for audit, so nothing changed; send it again with the same key. `CONFIGURATION_UNAVAILABLE` also uses this status. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
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
      "expectedProjectVersion": 1,
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
      "expectedProjectVersion": 1,
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
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Retries the same pinned release only after recovered or cancelled terminal state and after re-locking every environment against its original or compensated current deployment.

- Idempotency: required.
- An unrelated deployment or configuration change requires a new preview.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_RELEASE_GROUP_ID:?set POSTGRIP_RELEASE_GROUP_ID to a percent-encoded path value}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  POST \
  --header \
  "Idempotency-Key: ${POSTGRIP_IDEMPOTENCY_KEY}" \
  "${POSTGRIP_API_URL}/api/v1/services/release-groups/${POSTGRIP_RELEASE_GROUP_ID}/retry" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/release-groups/" + url.PathEscape(os.Getenv("POSTGRIP_RELEASE_GROUP_ID")) + "/retry")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))

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
const url = new URL(baseUrl + "/api/v1/services/release-groups/" + encodeURIComponent(process.env.POSTGRIP_RELEASE_GROUP_ID ?? "") + "/retry");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,  "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/release-groups/' + urllib.parse.quote(os.environ['POSTGRIP_RELEASE_GROUP_ID'], safe='') + '/retry'
request = urllib.request.Request(endpoint, method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")

request.add_header('Idempotency-Key', os.environ["POSTGRIP_IDEMPOTENCY_KEY"])
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
- [previewServiceReleaseGroup](./previewServiceReleaseGroup.md) — Preview and fence a multi-project release

[Back to Service index](./README.md)
