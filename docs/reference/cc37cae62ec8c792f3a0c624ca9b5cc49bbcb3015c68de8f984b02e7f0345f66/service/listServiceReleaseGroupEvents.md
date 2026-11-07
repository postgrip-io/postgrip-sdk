# List coordinated release events

`GET /api/v1/services/release-groups/{releaseGroupId}/events` · `listServiceReleaseGroupEvents` · Service

> Contract bundle `cc37cae62ec8c792f3a0c624ca9b5cc49bbcb3015c68de8f984b02e7f0345f66`
> Service contract `1a03ed98a794cbce8a45d413e51db982d7b72dc1b4dcaf71452b553fbea9b16a`

Returns the bounded append-only event history for release creation, dispatch, verification, cancellation, compensation, retry, and completion.

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
| `releaseGroupId` | path | yes | `string (uuid)` | `"11111111-1111-4111-8111-111111111111"` | Durable multi-project release saga identifier. |
| `limit` | query | no | `integer` | `1` | Page size. A missing, non-numeric, zero or negative value means 100, and a value above 100 means 100; neither is refused. |
| `cursor` | query | no | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Release group events | `application/json` | `ServiceReleaseGroupEventList` |
| `404` | Not found. `RELEASE_GROUP_NOT_FOUND`: no release group with that id exists in your organization, or the id is not a UUID. | `application/json` | `ErrorResponse` |
| `default` | Error | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "createdAt": "2026-01-01T00:00:00Z",
      "id": "11111111-1111-4111-8111-111111111111",
      "kind": "created",
      "state": "string"
    }
  ],
  "nextCursor": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns the bounded append-only event history for release creation, dispatch, verification, cancellation, compensation, retry, and completion.

- Treat cursors as opaque; event details are safe summaries and never contain Worker-local secrets.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_SERVICE_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_RELEASE_GROUP_ID:?set POSTGRIP_RELEASE_GROUP_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/services/release-groups/${POSTGRIP_RELEASE_GROUP_ID}/events" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_SERVICE_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/services/release-groups/" + url.PathEscape(os.Getenv("POSTGRIP_RELEASE_GROUP_ID")) + "/events")
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
const url = new URL(baseUrl + "/api/v1/services/release-groups/" + encodeURIComponent(process.env.POSTGRIP_RELEASE_GROUP_ID ?? "") + "/events");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_SERVICE_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/services/release-groups/' + urllib.parse.quote(os.environ['POSTGRIP_RELEASE_GROUP_ID'], safe='') + '/events'
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
- [listServiceReleaseGroups](./listServiceReleaseGroups.md) — List release groups
- [previewServiceReleaseGroup](./previewServiceReleaseGroup.md) — Preview and fence a multi-project release
- [retryServiceReleaseGroup](./retryServiceReleaseGroup.md) — Retry a safely recovered release group

[Back to Service index](./README.md)
