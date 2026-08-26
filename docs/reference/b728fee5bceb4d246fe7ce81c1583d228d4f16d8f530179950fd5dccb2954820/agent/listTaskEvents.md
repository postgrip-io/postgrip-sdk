# List a task's event stream

`GET /api/v1/tasks/{taskId}/events` · `listTaskEvents` · Agent

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Agent contract `d9df466806e58ae32ab98f6622086d49749672258af902bdf3777a061fef28ff`

Returns the task's full event history in order -- lease, start, heartbeat, stdout, stderr, and terminal events. This endpoint is not paginated.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Tasks` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token`, `agent-session` |
| Required scopes | `[["agent:logs:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `taskId` | path | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Task events | `application/json` | `array<TaskEvent>` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
    "created_at": "2026-01-01T00:00:00Z",
    "id": "string",
    "kind": "progress",
    "task_id": "string"
  }
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns the task's full event history in order -- lease, start, heartbeat, stdout, stderr, and terminal events. This endpoint is not paginated.

- No additional lifecycle constraint is recorded.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_TASK_ID:?set POSTGRIP_TASK_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/tasks/${POSTGRIP_TASK_ID}/events" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/tasks/" + url.PathEscape(os.Getenv("POSTGRIP_TASK_ID")) + "/events")
if err != nil { return err }
var body io.Reader
request, err := http.NewRequestWithContext(ctx, "GET", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))


response, err := http.DefaultClient.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/tasks/" + encodeURIComponent(process.env.POSTGRIP_TASK_ID ?? "") + "/events");

const response = await fetch(url, {
  method: "GET",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/tasks/' + urllib.parse.quote(os.environ['POSTGRIP_TASK_ID'], safe='') + '/events'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


with urllib.request.urlopen(request) as response:
    result = json.load(response)
```

## Related operations

- [enqueueTask](./enqueueTask.md) — Enqueue a task
- [getTask](./getTask.md) — Fetch a single task
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks
- [listTasks](./listTasks.md) — List tasks

[Back to Agent index](./README.md)
