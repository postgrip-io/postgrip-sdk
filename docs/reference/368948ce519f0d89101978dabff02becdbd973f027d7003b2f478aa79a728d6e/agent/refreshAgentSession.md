# Exchange a refresh token for a new agent session

`POST /api/v1/agent/session/refresh` · `refreshAgentSession` · Agent

> Contract bundle `368948ce519f0d89101978dabff02becdbd973f027d7003b2f478aa79a728d6e`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

The refresh token in the body is itself the credential, so this operation carries no bearer token. Rotation is single-use: presenting a token that has already been rotated revokes the whole token family.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Agent runtime` |
| Operation class | `agent-runtime` |
| Safety | `mutation` |
| Protocol | `http-json` |
| Credentials | `agent-refresh-token` |
| Required scopes | `[]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

This operation has no path or query parameters.

## Request body

Content type: `application/json` · Schema: `RefreshAgentSessionRequest`

```json
{
  "refreshToken": "string"
}
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `200` | Refreshed delegated session | `application/json` | `AgentSessionResponse` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "accessExpiresAt": "2026-01-01T00:00:00Z",
  "accessToken": "string",
  "agentId": "string",
  "refreshExpiresAt": "2026-01-01T00:00:00Z",
  "refreshToken": "string",
  "status": "string",
  "tenantId": "string",
  "tokenFamilyId": "string",
  "trustState": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

The refresh token in the body is itself the credential, so this operation carries no bearer token. Rotation is single-use: presenting a token that has already been rotated revokes the whole token family.

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
- [heartbeatAgentTask](./heartbeatAgentTask.md) — Extend a leased task's lease
- [pollAgentTask](./pollAgentTask.md) — Long-poll for the next leased task or lifecycle directive

[Back to Agent index](./README.md)
