# Extend a leased task's lease

`POST /api/v1/agent/tasks/{taskId}/heartbeat` · `heartbeatAgentTask` · Agent

> Contract bundle `0fd58ddbe2da2928c78655bb5d3909020acb547de2f6959e9acb7181e8e81047`
> Agent contract `ff3811f5561777a76363ee2e5a49ba40bcaff6d6fdaf2d834862dd56b5d58f3f`

Extends the lease and appends a heartbeat event. The task must currently be leased to the calling agent. When the task was cancelled (cancelTask) while this agent held it, the heartbeat, like every other mutation of the task, answers `409 TASK_CANCELLED`: stop the task and report nothing. Its message still says the task is terminal.

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
| `409` | `TASK_CANCELLED`: the task was cancelled; stop running it. `CONFLICT`: the task is terminal for another reason or no longer leased to this agent. | `application/json` | `ErrorResponse` |
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

Extends the lease and appends a heartbeat event. The task must currently be leased to the calling agent. A task cancelled with cancelTask answers this and every other mutation `409 TASK_CANCELLED`, whose message still says the task is terminal: stop the task and report nothing.

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
