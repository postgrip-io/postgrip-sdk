# Park a leased task until its workflow is signalled

`POST /api/v1/agent/tasks/{taskId}/block` · `blockAgentTask` · Agent

> Contract bundle `782f9c8e8e4d1678cbf527943abc2b4534abfe42b01525aabd6483b2c499d98d`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Non-terminal: the task moves to blocked and its lease is released, so it is not retried and no longer counts against the agent. A worker calls this whenever a workflow body suspends on a pending durable command -- an activity, a timer, a child workflow, or an awaited signal. The orchestrator re-queues the task for redelivery as soon as that dependency resolves: the activity completes, fails, or times out; the timer fires; the child workflow finishes; a signal or workflow update arrives; or the workflow is cancelled.

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

Content type: `application/json` · Schema: `BlockTaskRequest`

```json
{
  "reason": "string"
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

Non-terminal: the task moves to blocked and its lease is released, so it is not retried and no longer counts against the agent. A worker calls this whenever a workflow body suspends on a pending durable command -- an activity, a timer, a child workflow, or an awaited signal. The orchestrator re-queues the task for redelivery as soon as that dependency resolves: the activity completes, fails, or times out; the timer fires; the child workflow finishes; a signal or workflow update arrives; or the workflow is cancelled.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Stock cURL is not the conformance runner for this operation: Delegated Agent runtime requests require session claims and request signing.

Runner: `signed-agent-runtime` · Owner: `sdk-maintainers`.

## Protocol adapter

Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.
Use the typed Agent adapter and the `signed-agent-runtime` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.

## Related operations

- [appendAgentTaskEvent](./appendAgentTaskEvent.md) — Append an event to a leased task
- [completeAgentTask](./completeAgentTask.md) — Complete a leased task successfully
- [failAgentTask](./failAgentTask.md) — Fail a leased task
- [heartbeatAgentTask](./heartbeatAgentTask.md) — Extend a leased task's lease
- [pollAgentTask](./pollAgentTask.md) — Long-poll for the next leased task or lifecycle directive
- [refreshAgentSession](./refreshAgentSession.md) — Exchange a refresh token for a new agent session

[Back to Agent index](./README.md)
