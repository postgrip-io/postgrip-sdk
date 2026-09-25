# Signal a workflow, starting it first if none is running

`POST /api/v1/workflows/{workflowId}/signal-with-start` · `signalWithStartWorkflow` · Agent

> Contract bundle `81115f92f58149535f5fad0cadfb036d5ebb734542e2ff91787bb5eb95d1003d`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Starts a new execution of workflowType when no running one exists, then delivers the signal. A workflowId in the body takes precedence over the one in the path.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Workflows` |
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
| `workflowId` | path | yes | `string` | `"string"` | — |

## Request body

Content type: `application/json` · Schema: `SignalWithStartWorkflowRequest`

```json
{
  "signal": {
    "name": "string"
  },
  "workflowType": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Workflow execution and history event | `application/json` | `SignalWithStartWorkflowResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "signal": {
    "created_at": "2026-01-01T00:00:00Z",
    "id": "string",
    "type": "string",
    "workflow_id": "string"
  },
  "task": {
    "attempt": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "id": "string",
    "lease_timeout_seconds": 1,
    "namespace": "string",
    "queue": "string",
    "state": "queued",
    "type": "string",
    "updated_at": "2026-01-01T00:00:00Z"
  },
  "workflow": {
    "created_at": "2026-01-01T00:00:00Z",
    "id": "string",
    "namespace": "string",
    "queue": "string",
    "run_id": "string",
    "state": "running",
    "task_id": "string",
    "type": "string",
    "updated_at": "2026-01-01T00:00:00Z"
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Starts a new execution of workflowType when no running one exists, then delivers the signal. A workflowId in the body takes precedence over the one in the path.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKFLOW_ID:?set POSTGRIP_WORKFLOW_ID to a percent-encoded path value}"
POSTGRIP_BODY_FILE="$(mktemp)"
chmod 600 "${POSTGRIP_BODY_FILE}"
trap 'rm -f "${POSTGRIP_BODY_FILE}"' EXIT
cat >"${POSTGRIP_BODY_FILE}" <<'POSTGRIP_JSON'
{
  "signal": {
    "name": "string"
  },
  "workflowType": "string"
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
  "${POSTGRIP_API_URL}/api/v1/workflows/${POSTGRIP_WORKFLOW_ID}/signal-with-start" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workflows/" + url.PathEscape(os.Getenv("POSTGRIP_WORKFLOW_ID")) + "/signal-with-start")
if err != nil { return err }
body := strings.NewReader("{\"signal\":{\"name\":\"string\"},\"workflowType\":\"string\"}")
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
const url = new URL(baseUrl + "/api/v1/workflows/" + encodeURIComponent(process.env.POSTGRIP_WORKFLOW_ID ?? "") + "/signal-with-start");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"signal\":{\"name\":\"string\"},\"workflowType\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workflows/' + urllib.parse.quote(os.environ['POSTGRIP_WORKFLOW_ID'], safe='') + '/signal-with-start'
request = urllib.request.Request(endpoint, data='{"signal":{"name":"string"},"workflowType":"string"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None

with urllib.request.build_opener(_NoRedirect()).open(request) as response:
    result = json.load(response)
```

## Related operations

- [cancelWorkflow](./cancelWorkflow.md) — Request cooperative cancellation of a workflow
- [countWorkflows](./countWorkflows.md) — Count workflow executions matching a filter
- [getWorkflow](./getWorkflow.md) — Fetch a workflow execution
- [listWorkflowHistory](./listWorkflowHistory.md) — List a workflow's history events
- [listWorkflows](./listWorkflows.md) — List workflow executions
- [signalWorkflow](./signalWorkflow.md) — Send a signal to a running workflow
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
