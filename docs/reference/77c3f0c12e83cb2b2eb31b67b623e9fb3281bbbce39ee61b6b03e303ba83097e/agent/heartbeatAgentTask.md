# Extend a leased task's lease

`POST /api/v1/agent/tasks/{taskId}/heartbeat` · `heartbeatAgentTask` · Agent

> Contract bundle `77c3f0c12e83cb2b2eb31b67b623e9fb3281bbbce39ee61b6b03e303ba83097e`
> Agent contract `0afbde31bd07059bc872324c82711bb8284fba1722c5bf9aa6b7cf76a42f7060`

Extends the lease and appends a heartbeat event. The task must currently be leased to the calling agent.

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

Content type: `application/json` · Schema: `HeartbeatTaskRequest`

```json
{
  "event": {
    "kind": "progress"
  },
  "lease_timeout_seconds": 1
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Task | `application/json` | `Task` |
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

Extends the lease and appends a heartbeat event. The task must currently be leased to the calling agent.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Stock cURL is not the conformance runner for this operation: Delegated Agent runtime requests require session claims and request signing.

Runner: `signed-agent-runtime` · Owner: `sdk-maintainers`.

## Protocol adapter

Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.
Use the typed Agent adapter and the `signed-agent-runtime` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.

## Related operations

- [appendAgentTaskEvent](./appendAgentTaskEvent.md) — Append an event to a leased task
- [blockAgentTask](./blockAgentTask.md) — Park a leased task until its workflow is signalled
- [completeAgentTask](./completeAgentTask.md) — Complete a leased task successfully
- [failAgentTask](./failAgentTask.md) — Fail a leased task
- [pollAgentTask](./pollAgentTask.md) — Long-poll for the next leased task or lifecycle directive
- [refreshAgentSession](./refreshAgentSession.md) — Exchange a refresh token for a new agent session

[Back to Agent index](./README.md)
