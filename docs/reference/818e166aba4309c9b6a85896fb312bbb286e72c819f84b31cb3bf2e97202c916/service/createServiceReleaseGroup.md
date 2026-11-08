# Create a coordinated release group

`POST /api/v1/services/release-groups` · `createServiceReleaseGroup` · Service

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Service contract `95872979a1e84bd2915f33ce6c2326aec2e0cf77ba2e474f65e08d619efbe439`

Accepts an unexpired preview and creates one durable release identity. Dependency-ready members dispatch in parallel. A required failure cancels safe work and restores already-cut-over reversible members; non-reversible cutovers report intervention-required.

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
| `Idempotency-Key` | header | yes | `string` | `"recorded"` | — |

## Request body

Content type: `application/json` · Schema: `CreateServiceReleaseGroupRequest`

```json
{
  "previewToken": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Release group accepted | `application/json` | `ServiceReleaseGroup` |
| `409` | Conflict. `RELEASE_OVERLAP`: another active release group already includes one of the environments; wait for it to end, or cancel it, then preview again. `SERVICE_STATE_CHANGED`: the preview token is older than 10 minutes, damaged or not your organization's, or a member's service or environment settings, Worker or current deployment changed after the preview; preview again and create with a new key. Other conflicts on this route also use this status. | `application/json` | `ErrorResponse` |
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

Creates one durable tenant-scoped saga from an unexpired preview and dispatches dependency-ready members while preserving exact per-member deployment identities.

- Idempotency: required.
- A second active release targeting any member environment is rejected, and canonical forward traffic remains fenced until aggregate success.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_IDEMPOTENCY_KEY:?set POSTGRIP_IDEMPOTENCY_KEY for this request}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "previewToken": "string"
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
body := strings.NewReader("{\"previewToken\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/services/release-groups");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json", "Idempotency-Key": process.env.POSTGRIP_IDEMPOTENCY_KEY, },
  body: "{\"previewToken\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/release-groups'
request = urllib.request.Request(endpoint, data='{"previewToken":"string"}'.encode(), method='POST')
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

- [cancelServiceReleaseGroup](./cancelServiceReleaseGroup.md) — Cancel and compensate a release group
- [getServiceReleaseGroup](./getServiceReleaseGroup.md) — Get aggregate and per-member release state
- [listServiceReleaseGroupEvents](./listServiceReleaseGroupEvents.md) — List bounded release audit events
- [listServiceReleaseGroups](./listServiceReleaseGroups.md) — List release groups
- [previewServiceReleaseGroup](./previewServiceReleaseGroup.md) — Preview and fence a multi-project release
- [retryServiceReleaseGroup](./retryServiceReleaseGroup.md) — Retry a safely recovered release group

[Back to Service index](./README.md)
