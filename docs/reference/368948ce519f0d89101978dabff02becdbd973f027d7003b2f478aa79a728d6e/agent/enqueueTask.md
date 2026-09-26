# Enqueue a task

`POST /api/v1/tasks` · `enqueueTask` · Agent

> Contract bundle `368948ce519f0d89101978dabff02becdbd973f027d7003b2f478aa79a728d6e`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Returns 202 with the created task. Any tenantId in the body is replaced with the tenant the credential resolves to.

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

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `EnqueueTaskRequest`

```json
{
  "type": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Task | `application/json` | `Task` |
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

Returns 202 with the created task. Any tenantId in the body is replaced with the tenant the credential resolves to.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "type": "string"
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
body := strings.NewReader("{\"type\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/tasks");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"type\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/tasks'
request = urllib.request.Request(endpoint, data='{"type":"string"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [getTask](./getTask.md) — Fetch a single task
- [listTaskEvents](./listTaskEvents.md) — List a task's event stream
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks
- [listTasks](./listTasks.md) — List tasks

[Back to Agent index](./README.md)
