# List workflow executions

`GET /api/v1/workflows` · `listWorkflows` · Agent

> Contract bundle `52dd8258f8b5481d0619ba4a4a1f8e4d17398a245704067a27458ba3860734a2`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Uses the contract-defined GET /api/v1/workflows behavior.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Workflows` |
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
| `id` | query | no | `string` | `"string"` | — |
| `run_id` | query | no | `string` | `"string"` | — |
| `type` | query | no | `string` | `"string"` | — |
| `queue` | query | no | `string` | `"string"` | — |
| `state` | query | no | `WorkflowState` | `"running"` | — |
| `query` | query | no | `string` | `"string"` | — |
| `q` | query | no | `string` | `"string"` | Compatibility alias for query. |
| `agent_id` | query | no | `string` | `"string"` | Compatibility identifier; authenticated requests derive the agent from the session token. |
| `order_by` | query | no | `string` | `"string"` | — |
| `order` | query | no | `string` | `"string"` | Compatibility alias for order_by. |
| `page_token` | query | no | `string` | `"string"` | — |
| `search.*` | query | no | `JsonValue` | `"string"` | Search-attribute filter; replace * with the attribute name. |
| `limit` | query | no | `integer` | `1` | — |
| `offset` | query | no | `integer` | `1` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Workflow executions | `application/json` | `array<WorkflowExecution>` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
[
  {
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
]
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Uses the contract-defined GET /api/v1/workflows behavior.

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
  "${POSTGRIP_API_URL}/api/v1/workflows" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workflows")
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
const url = new URL(baseUrl + "/api/v1/workflows");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workflows'
request = urllib.request.Request(endpoint, method='GET')
request.add_header('Authorization', f"Bearer {os.environ['POSTGRIP_TOKEN']}")


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
- [signalWithStartWorkflow](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [signalWorkflow](./signalWorkflow.md) — Send a signal to a running workflow
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
