# Cancel a task

`POST /api/v1/tasks/{taskId}/cancel` · `cancelTask` · Agent

> Contract bundle `a20586b1bf0a44746bca6b9d4fd8511a50be823ca55450324efd077ebaca00f5`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

Ends a task that has not finished: it becomes `failed` at once, with `error` `task cancelled` (or `task cancelled: <reason>`), `result.failure.type` `TaskCancelled` and a `failed` event with stage `cancelled`. A `queued` task is never leased. A `leased` task's Agent learns of the cancel on its next heartbeat, which answers `409 TASK_CANCELLED`, and stops the task's process and the processes it started; its result is refused, so the task stays cancelled. This is how a `workflow.runtime` task is stopped. Cancelling a task that is already cancelled answers it unchanged, so a resend is safe. A task that already finished answers `409 TASK_TERMINAL` with `details.state`, and a workflow's own task (a `workflow:`, `activity:`, `query:` or `update:` type, or `timer`) `409 TASK_OWNED_BY_WORKFLOW`: cancel its workflow instead. A task belonging to another tenant is reported as 404, as getTask does.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Tasks` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `postgrip-token`, `agent-session` |
| Required scopes | `[["agent:operate"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `taskId` | path | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `CancelTaskRequest`

```json
{
  "reason": "superseded by build 4513"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Task | `application/json` | `Task` |
| `409` | `TASK_TERMINAL`: the task already finished, and `details.state` says how. `TASK_OWNED_BY_WORKFLOW`: the task belongs to a workflow; cancel or terminate the workflow instead. | `application/json` | `ErrorResponse` |
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

Ends a task that has not finished: it becomes `failed` at once, with `error` `task cancelled` (or `task cancelled: <reason>`) and `result.failure.type` `TaskCancelled`. A leased task's Agent learns of it on its next heartbeat, which answers `409 TASK_CANCELLED`, and stops it; its later reports are refused. Cancelling a cancelled task answers it unchanged, so a resend is safe without an idempotency key. A finished task answers `409 TASK_TERMINAL` with `details.state`, a workflow's own task `409 TASK_OWNED_BY_WORKFLOW`, and another tenant's task 404.

- Cancel only a task the test enqueued; a workflow's task is refused, so cancel its workflow instead.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_TASK_ID:?set POSTGRIP_TASK_ID to a percent-encoded path value}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "reason": "superseded by build 4513"
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
  "${POSTGRIP_API_URL}/api/v1/tasks/${POSTGRIP_TASK_ID}/cancel" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/tasks/" + url.PathEscape(os.Getenv("POSTGRIP_TASK_ID")) + "/cancel")
if err != nil { return err }
body := strings.NewReader("{\"reason\":\"superseded by build 4513\"}")
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
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/tasks/" + encodeURIComponent(process.env.POSTGRIP_TASK_ID ?? "") + "/cancel");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"reason\":\"superseded by build 4513\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/tasks/' + urllib.parse.quote(os.environ['POSTGRIP_TASK_ID'], safe='') + '/cancel'
request = urllib.request.Request(endpoint, data='{"reason":"superseded by build 4513"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

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
- [listTasks](./listTasks.md) — List tasks

[Back to Agent index](./README.md)
