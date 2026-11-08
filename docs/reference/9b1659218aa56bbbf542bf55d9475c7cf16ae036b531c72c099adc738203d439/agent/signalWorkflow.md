# Send a signal to a running workflow

`POST /api/v1/workflows/{workflowId}/signal` · `signalWorkflow` · Agent

> Contract bundle `9b1659218aa56bbbf542bf55d9475c7cf16ae036b531c72c099adc738203d439`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

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
| Idempotency | `optional` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `workflowId` | path | yes | `string` | `"string"` | — |
| `Idempotency-Key` | header | no | `string` | `"recorded"` | Makes the request safe to send again for 24 hours: 1 to 128 visible ASCII characters, unique to this request. A resend with the same key and the same request answers the stored status and body with `Idempotent-Replayed: true` and runs nothing again. The same key with another method, path or body answers `409 IDEMPOTENCY_CONFLICT`, and a resend while the first request still runs `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After`. Only a 2xx answer and a 400 refusal are kept; any other answer releases the key, so a resend after its cause is fixed runs again. A key belongs to the credential that sent it and the operation: another token, user or Agent, or another operation, never sees it. Without the header every request runs. |

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
| `409` | The workflow is no longer running (`CONFLICT`, which does not keep the key), or, with an `Idempotency-Key`, `IDEMPOTENCY_CONFLICT` or `IDEMPOTENCY_IN_PROGRESS`. | `application/json` | `ErrorResponse` |
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

- Idempotency: optional; send an Idempotency-Key to make a resend answer the stored result (`Idempotent-Replayed: true`) instead of running again. A reused key with another request answers `409 IDEMPOTENCY_CONFLICT`, one still running `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After`.
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

client := &http.Client{
    CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}
response, err := client.Do(request)
```

### TypeScript

```ts
const baseUrl = process.env.POSTGRIP_AGENT_URL ?? process.env.POSTGRIP_URL;
if (!baseUrl) throw new Error("configure POSTGRIP_URL");
const url = new URL(baseUrl + "/api/v1/workflows/" + encodeURIComponent(process.env.POSTGRIP_WORKFLOW_ID ?? "") + "/signal");

const response = await fetch(url, {
  method: "POST",
  redirect: "manual",
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
- [signalWithStartWorkflow](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [terminateWorkflow](./terminateWorkflow.md) — Forcibly terminate a workflow

[Back to Agent index](./README.md)
