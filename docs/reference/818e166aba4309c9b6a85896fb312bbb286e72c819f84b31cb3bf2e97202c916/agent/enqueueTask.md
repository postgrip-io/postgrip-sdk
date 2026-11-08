# Enqueue a task

`POST /api/v1/tasks` · `enqueueTask` · Agent

> Contract bundle `818e166aba4309c9b6a85896fb312bbb286e72c819f84b31cb3bf2e97202c916`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

Returns 202 with the created task. Any tenantId in the body is replaced with the tenant the credential resolves to. A payload that carries a plaintext credential is refused with 400 PLAINTEXT_SECRET_REJECTED and nothing is stored. A shell.exec or container.exec task names its secrets in a top-level secret_env instead, mapping environment variables to secrets in the executing Agent's local store, and is leased only to Agents that advertise task_secret_env (see EnqueueTaskRequest.payload). A `workflow:` task whose payload sets a search attribute that starts with `postgrip.` is refused with 400 INVALID_REQUEST naming the attribute; that prefix is reserved for attributes PostGrip sets, such as `postgrip.scheduleId`. Any `type` is accepted: a custom type is leased only by a client that polls for it (see EnqueueTaskRequest.type).

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
| Idempotency | `optional` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `Idempotency-Key` | header | no | `string` | `"recorded"` | Makes the request safe to send again for 24 hours: 1 to 128 visible ASCII characters, unique to this request. A resend with the same key and the same request answers the stored status and body with `Idempotent-Replayed: true` and runs nothing again. The same key with another method, path or body answers `409 IDEMPOTENCY_CONFLICT`, and a resend while the first request still runs `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After`. Only a 2xx answer and a 400 refusal are kept; any other answer releases the key, so a resend after its cause is fixed runs again. A key belongs to the credential that sent it and the operation: another token, user or Agent, or another operation, never sees it. Without the header every request runs. |

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
| `409` | With an `Idempotency-Key`: `IDEMPOTENCY_CONFLICT` for a key already used with another request, `IDEMPOTENCY_IN_PROGRESS` while the first request with the key still runs. A `workflow:` task whose `workflowId` names an existing run answers `409 CONFLICT` (`workflowIdReusePolicy`), and does not keep the key. | `application/json` | `ErrorResponse` |
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

- Idempotency: optional; send an Idempotency-Key to make a resend answer the stored result (`Idempotent-Replayed: true`) instead of running again. A reused key with another request answers `409 IDEMPOTENCY_CONFLICT`, one still running `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After`.
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

- [cancelTask](./cancelTask.md) — Cancel a task
- [getTask](./getTask.md) — Fetch a single task
- [listTaskEvents](./listTaskEvents.md) — List a task's event stream
- [listTaskEventsBatch](./listTaskEventsBatch.md) — List recent events for multiple tasks
- [listTasks](./listTasks.md) — List tasks

[Back to Agent index](./README.md)
