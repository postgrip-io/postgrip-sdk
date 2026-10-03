# Fetch a single task

`GET /api/v1/tasks/{taskId}` · `getTask` · Agent

> Contract bundle `5554b3e409eda9d29eaf30f7e465e3ee352a55ebc68060b58cbfe356ff1c6af8`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

A task belonging to another tenant is reported as 404 rather than 403, so identifiers cannot be probed across tenant boundaries.

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
| `taskId` | path | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Task | `application/json` | `Task` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
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
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

A task belonging to another tenant is reported as 404 rather than 403, so identifiers cannot be probed across tenant boundaries.

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
  "${POSTGRIP_API_URL}/api/v1/tasks/${POSTGRIP_TASK_ID}" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/tasks/" + url.PathEscape(os.Getenv("POSTGRIP_TASK_ID")))
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
const url = new URL(baseUrl + "/api/v1/tasks/" + encodeURIComponent(process.env.POSTGRIP_TASK_ID ?? ""));

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/tasks/' + urllib.parse.quote(os.environ['POSTGRIP_TASK_ID'], safe='')
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
- [listTaskEvents](./listTaskEvents.md) — List a task's event stream
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks
- [listTasks](./listTasks.md) — List tasks

[Back to Agent index](./README.md)
