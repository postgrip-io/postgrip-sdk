# Send a signal to a running workflow

`POST /api/v1/workflows/{workflowId}/signal` · `signalWorkflow` · Agent

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Agent contract `d9df466806e58ae32ab98f6622086d49749672258af902bdf3777a061fef28ff`

Returns 202 with the appended history event. A signal also releases the workflow's blocked task, which is how a task that parked itself resumes. Signalling a workflow that is no longer running fails.

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

Content type: `application/json` · Schema: `SignalWorkflowRequest`

```json
{
  "name": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Workflow history event | `application/json` | `WorkflowHistoryEvent` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "created_at": "2026-01-01T00:00:00Z",
  "id": "string",
  "type": "string",
  "workflow_id": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns 202 with the appended history event. A signal also releases the workflow's blocked task, which is how a task that parked itself resumes. Signalling a workflow that is no longer running fails.

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
  "name": "string"
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
  "${POSTGRIP_API_URL}/api/v1/workflows/${POSTGRIP_WORKFLOW_ID}/signal" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workflows/" + url.PathEscape(os.Getenv("POSTGRIP_WORKFLOW_ID")) + "/signal")
if err != nil { return err }
body := strings.NewReader("{\"name\":\"string\"}")
request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), body)
if err != nil { return err }
request.Header.Set("Authorization", "Bearer "+os.Getenv("POSTGRIP_TOKEN"))
request.Header.Set("Content-Type", "application/json")

response, err := http.DefaultClient.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/workflows/" + encodeURIComponent(process.env.POSTGRIP_WORKFLOW_ID ?? "") + "/signal");

const response = await fetch(url, {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`, "Content-Type": "application/json",  },
  body: "{\"name\":\"string\"}"
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workflows/' + urllib.parse.quote(os.environ['POSTGRIP_WORKFLOW_ID'], safe='') + '/signal'
request = urllib.request.Request(endpoint, data='{"name":"string"}'.encode(), method='POST')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")
request.add_header('Content-Type', 'application/json')

with urllib.request.urlopen(request) as response:
    result = json.load(response)
```

## Related operations

- [cancelWorkflow](./cancelWorkflow.md) — Request cooperative cancellation of a workflow
- [countWorkflows](./countWorkflows.md) — Count workflow executions matching a filter
- [getWorkflow](./getWorkflow.md) — Fetch a workflow execution
- [listWorkflowHistory](./listWorkflowHistory.md) — List a workflow's history events
- [listWorkflows](./listWorkflows.md) — List workflow executions
- [signalWithStartWorkflow](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
