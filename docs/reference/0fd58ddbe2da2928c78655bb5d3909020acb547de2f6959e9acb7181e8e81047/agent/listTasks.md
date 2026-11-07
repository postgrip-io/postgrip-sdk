# List tasks

`GET /api/v1/tasks` · `listTasks` · Agent

> Contract bundle `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

Filters by namespace, queue, type, and state within the caller's tenant, then sorts and paginates. The answer is a bare array; to read the next page, send `offset` (or `page_token`, which is the same numeric offset) advanced by the number of tasks already read. `limit` has no maximum; without it every matching task is returned. An unknown `state` or `order_by` answers 400 INVALID_REQUEST with a message that names the parameter.

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
| `state` | query | no | `TaskState` | `"queued"` | One task state. Any other value answers 400. |
| `order_by` | query | no | `string` | `"string"` | `created_at`, `-created_at`, `updated_at` or `-updated_at`; a leading `-` sorts newest first. Without it, tasks keep insertion order. Any other value answers 400. |
| `page_token` | query | no | `string` | `"string"` | A numeric offset, used only when `offset` is absent. |
| `limit` | query | no | `integer` | `1` | — |
| `offset` | query | no | `integer` | `1` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Tasks, as a bare JSON array with no envelope and no next-page token. | `application/json` | `array<Task>` |
| `400` | An unknown `state` or `order_by`. The message names the parameter and the accepted values. | `application/json` | `ErrorResponse` |
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

- [cancelTask](./cancelTask.md) — Cancel a task
- [enqueueTask](./enqueueTask.md) — Enqueue a task
- [getTask](./getTask.md) — Fetch a single task
- [listTaskEvents](./listTaskEvents.md) — List a task's event stream
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks

[Back to Agent index](./README.md)
