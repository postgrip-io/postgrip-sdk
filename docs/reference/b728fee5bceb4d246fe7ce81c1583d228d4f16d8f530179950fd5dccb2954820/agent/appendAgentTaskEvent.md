# Append an event to a leased task

`POST /api/v1/agent/tasks/{taskId}/events` · `appendAgentTaskEvent` · Agent

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Agent contract `d9df466806e58ae32ab98f6622086d49749672258af902bdf3777a061fef28ff`

Records one task event and returns 202. Agents send progress, milestone, stdout, and stderr; the TypeScript and Python workers additionally emit started, completed, and failed markers alongside the authoritative complete and fail calls, so a finished task can carry two completed events. Only the server writes leased. The kind is not validated -- an empty value defaults to progress. This does not extend the lease; send a heartbeat for that.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agent runtime` |
| Operation class | `agent-runtime` |
| Safety | `mutation` |
| Protocol | `signed-agent-task-v1` |
| Credentials | `agent-session` |
| Required scopes | `[]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `taskId` | path | yes | `string` | `"string"` | — |
| `agent_id` | query | no | `string` | `"string"` | Compatibility identifier; authenticated requests derive the agent from the session token. |

## Request body

Content type: `application/json` · Schema: `AppendTaskEventRequest`

```json
{
  "event": {
    "kind": "progress"
  }
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `202` | Task event | `application/json` | `TaskEvent` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "created_at": "2026-01-01T00:00:00Z",
  "id": "string",
  "kind": "progress",
  "task_id": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Records one task event and returns 202. Agents send progress, milestone, stdout, and stderr; the TypeScript and Python workers additionally emit started, completed, and failed markers alongside the authoritative complete and fail calls, so a finished task can carry two completed events. Only the server writes leased. The kind is not validated -- an empty value defaults to progress. This does not extend the lease; send a heartbeat for that.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Stock cURL is not the conformance runner for this operation: Delegated Agent runtime requests require session claims and request signing.

Runner: `signed-agent-runtime` · Owner: `sdk-maintainers`.

## Protocol adapter

Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.
Use the typed Agent adapter and the `signed-agent-runtime` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.

## Related operations

- [blockAgentTask](./blockAgentTask.md) — Park a leased task until its workflow is signalled
- [completeAgentTask](./completeAgentTask.md) — Complete a leased task successfully
- [failAgentTask](./failAgentTask.md) — Fail a leased task
- [heartbeatAgentTask](./heartbeatAgentTask.md) — Extend a leased task's lease
- [pollAgentTask](./pollAgentTask.md) — Long-poll for the next leased task or lifecycle directive
- [refreshAgentSession](./refreshAgentSession.md) — Exchange a refresh token for a new agent session

[Back to Agent index](./README.md)
