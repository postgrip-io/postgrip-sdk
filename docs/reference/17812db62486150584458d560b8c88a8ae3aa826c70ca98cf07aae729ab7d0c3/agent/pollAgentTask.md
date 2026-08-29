# Long-poll for the next leased task or lifecycle directive

`GET /api/v1/agent/poll` · `pollAgentTask` · Agent

> Contract bundle `17812db62486150584458d560b8c88a8ae3aa826c70ca98cf07aae729ab7d0c3`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Blocks up to wait_seconds and returns 200 with an empty object -- not 204 -- when nothing is available. A queued lifecycle directive (upgrade, log level, attest) is returned in place of a task, and an agent that has been removed receives 410 carrying a shutdown directive.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agent runtime` |
| Operation class | `agent-runtime` |
| Safety | `read-only` |
| Protocol | `http-json` |
| Credentials | `agent-session` |
| Required scopes | `[]` |
| Idempotency | `none` |
| Retry | `bounded` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `namespace` | query | no | `string` | `"string"` | — |
| `queue` | query | yes | `string` | `"string"` | — |
| `agent_id` | query | no | `string` | `"string"` | Compatibility identifier; authenticated requests derive the agent from the session token. |
| `version` | query | no | `integer` | `1` | Current agent runtime version used to enforce upgrade policy. |
| `log_level` | query | no | `string` | `"debug"` | Current agent log level used to synchronize runtime configuration. |
| `capabilities` | query | no | `array<string>` | `["string"]` | Runtime and isolation capabilities advertised by the agent. The server accepts repeated or comma-separated values. |
| `wait_seconds` | query | no | `integer` | `1` | — |
| `task_types` | query | no | `string` | `"string"` | Comma-separated task types. |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Leased task, if available | `application/json` | `PollTaskResponse` |
| `410` | The agent has been removed. The body carries a shutdown directive and the agent should stop polling and exit. | `application/json` | `PollTaskResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "directive": {
    "type": "upgrade"
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
  }
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Blocks up to wait_seconds and returns 200 with an empty object -- not 204 -- when nothing is available. A queued lifecycle directive (upgrade, log level, attest) is returned in place of a task, and an agent that has been removed receives 410 carrying a shutdown directive.

- No additional lifecycle constraint is recorded.

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
- [heartbeatAgentTask](./heartbeatAgentTask.md) — Extend a leased task's lease
- [refreshAgentSession](./refreshAgentSession.md) — Exchange a refresh token for a new agent session

[Back to Agent index](./README.md)
