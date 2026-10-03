# Count workflow executions matching a filter

`GET /api/v1/workflows/count` · `countWorkflows` · Agent

> Contract bundle `da4b4d4b5af748ee197815878cee6e35d23ce9a98883a8fd38fce642eb53ab0b`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Applies the same filters as the list operation and returns only the count. Paging parameters are ignored.

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
| `search.*` | query | no | `JsonValue` | `"string"` | Search-attribute filter; replace * with the attribute name. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Workflow count | `application/json` | `WorkflowCountResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "count": 1
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Applies the same filters as the list operation and returns only the count. Paging parameters are ignored.

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
  "${POSTGRIP_API_URL}/api/v1/workflows/count" <<EOF
header = "Authorization: Bearer ${POSTGRIP_TOKEN}"
EOF
```

## Equivalent raw HTTP

These snippets expose the exact wire request for agents and tools. Prefer the typed plane client in application code.

### Go

```go
baseURL := os.Getenv("POSTGRIP_AGENT_URL")
if baseURL == "" { baseURL = os.Getenv("POSTGRIP_URL") }
endpoint, err := url.Parse(baseURL + "/api/v1/workflows/count")
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
const url = new URL(baseUrl + "/api/v1/workflows/count");

const response = await fetch(url, {
  method: "GET",
  redirect: "manual",
  headers: { Authorization: `Bearer ${process.env.POSTGRIP_TOKEN}`,   }
});
```

### Python

```python
base_url = os.environ.get("POSTGRIP_AGENT_URL") or os.environ["POSTGRIP_URL"]
endpoint = base_url + '/api/v1/workflows/count'
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
- [getWorkflow](./getWorkflow.md) — Fetch a workflow execution
- [listWorkflowHistory](./listWorkflowHistory.md) — List a workflow's history events
- [listWorkflows](./listWorkflows.md) — List workflow executions
- [signalWithStartWorkflow](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [signalWorkflow](./signalWorkflow.md) — Send a signal to a running workflow
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
