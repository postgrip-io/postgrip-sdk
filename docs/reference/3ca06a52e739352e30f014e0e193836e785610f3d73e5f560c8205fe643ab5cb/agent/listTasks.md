# List tasks

`GET /api/v1/tasks` · `listTasks` · Agent

> Contract bundle `3ca06a52e739352e30f014e0e193836e785610f3d73e5f560c8205fe643ab5cb`
> Agent contract `0afbde31bd07059bc872324c82711bb8284fba1722c5bf9aa6b7cf76a42f7060`

Filters by namespace, queue, type, and state within the caller's tenant, then sorts and paginates.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Tasks` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token`, `agent-session` |
| Required scopes | `[["agent:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `namespace` | query | no | `string` | `"string"` | — |
| `queue` | query | no | `string` | `"string"` | — |
| `type` | query | no | `string` | `"string"` | — |
| `state` | query | no | `TaskState` | `"queued"` | — |
| `order_by` | query | no | `string` | `"string"` | — |
| `page_token` | query | no | `string` | `"string"` | — |
| `limit` | query | no | `integer` | `1` | — |
| `offset` | query | no | `integer` | `1` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Tasks | `application/json` | `array<Task>` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
    "attempt": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "id": "string",
    "lease_timeout_seconds": 1,
    "namespace": "string",
    "queue": "string",
    "state": "queued",
    "type": "string",
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Filters by namespace, queue, type, and state within the caller's tenant, then sorts and paginates.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
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
  "${POSTGRIP_API_URL}/api/v1/tasks" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/tasks")
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
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/tasks");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/tasks'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [enqueueTask](./enqueueTask.md) — Enqueue a task
- [getTask](./getTask.md) — Fetch a single task
- [listTaskEvents](./listTaskEvents.md) — List a task's event stream
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks

[Back to Agent index](./README.md)
