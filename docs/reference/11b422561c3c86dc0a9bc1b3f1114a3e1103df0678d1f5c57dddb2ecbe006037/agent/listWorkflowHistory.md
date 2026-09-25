# List a workflow's history events

`GET /api/v1/workflows/{workflowId}/history` · `listWorkflowHistory` · Agent

> Contract bundle `11b422561c3c86dc0a9bc1b3f1114a3e1103df0678d1f5c57dddb2ecbe006037`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Returns one stable cursor page for a single workflow run. Follow nextCursor until it is absent to consume the snapshot; a cursor remains bound to the original run if the workflow continues as new.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Workflows` |
| Operation class | `tenant-api` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `postgrip-token`, `agent-session` |
| Required scopes | `[["agent:logs:read"]]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `cursor` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workflowId` | path | yes | `string` | `"string"` | — |
| `cursor` | query | no | `string` | `"string"` | Opaque cursor returned as nextCursor by the preceding page. |
| `limit` | query | no | `integer` | `1` | Maximum number of events in one response page. The server may return fewer items to honor its serialized response-size bound. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Workflow history | `application/json` | `WorkflowHistoryPage` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "items": [
    {
      "created_at": "2026-01-01T00:00:00Z",
      "id": "string",
      "type": "string",
      "workflow_id": "string"
    }
  ]
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Returns one stable cursor page for a single workflow run. Follow nextCursor unchanged until it is absent; a fresh request is required to observe later history.

- The opaque cursor remains bound to the original run if the workflow continues as new.
- The server may return fewer than limit events to honor its serialized response-size bound.

## cURL

Requires cURL 7.76 or newer. The bearer is supplied over standard input and does not enter the process argument list.

```sh
set +x
POSTGRIP_API_URL="${POSTGRIP_AGENT_URL:-${POSTGRIP_URL}}"
: "${POSTGRIP_API_URL:?set POSTGRIP_URL or the plane-specific URL}"
: "${POSTGRIP_TOKEN:?set POSTGRIP_TOKEN}"
: "${POSTGRIP_WORKFLOW_ID:?set POSTGRIP_WORKFLOW_ID to a percent-encoded path value}"
curl \
  --config \
  - \
  --fail-with-body \
  --silent \
  --show-error \
  --request \
  GET \
  "${POSTGRIP_API_URL}/api/v1/workflows/${POSTGRIP_WORKFLOW_ID}/history" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workflows/" + url.PathEscape(os.Getenv("POSTGRIP_WORKFLOW_ID")) + "/history")
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
const url = new URL(baseUrl + "/api/v1/workflows/" + encodeURIComponent(process.env.POSTGRIP_WORKFLOW_ID ?? "") + "/history");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workflows/' + urllib.parse.quote(os.environ['POSTGRIP_WORKFLOW_ID'], safe='') + '/history'
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
- [listWorkflows](./listWorkflows.md) — List workflow executions
- [signalWithStartWorkflow](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [signalWorkflow](./signalWorkflow.md) — Send a signal to a running workflow
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
