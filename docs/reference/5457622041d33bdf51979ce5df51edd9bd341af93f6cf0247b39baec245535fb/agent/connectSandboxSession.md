# Attach to an interactive session over WebSocket

`GET /api/v1/sandbox-sessions/{sessionId}/connect` · `connectSandboxSession` · Agent

> Contract bundle `5457622041d33bdf51979ce5df51edd9bd341af93f6cf0247b39baec245535fb`
> Agent contract `86aa7d831437544f83f26486212b297565f621d784f2850c5c9af391e3f68018`

Upgrades to the one-shot WebSocket stream authorized by the ticket. For pty and exec sessions, binary messages carry raw stdin/stdout bytes and stdout/stderr are interleaved. postgrip.sandbox.terminal.v1 reserves client-to-agent text frames for strict resize JSON of the form {"type":"resize","rows":24,"columns":80}; postgrip.sandbox.terminal.v2 applies strict JSON control framing in both directions and additionally permits agent-to-client notice messages of the form {"type":"notice","code":"session_ready","message":"Sandbox stream is ready"}. Rows and columns must be integers from 1 through 65535. A zero-length client binary message signals terminal stdin EOF without closing output. Without a negotiated terminal protocol, text messages remain legacy raw stdin. Exec exit codes, and only exec exit codes, use WebSocket close status 4000 plus the process code. For port sessions, postgrip.sandbox.port.v1 carries raw TCP bytes in binary messages; text messages are invalid, and terminal controls and terminal close-code semantics do not apply. Ping/Pong liveness is enforced independently on every proxy hop, and any failed hop terminates both relay peers.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Sandboxes` |
| Operation class | `tenant-api` |
| Safety | `protocol` |
| Protocol | `websocket` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:operate"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `sessionId` | path | yes | `string` | `"string"` | — |
| `ticket` | query | yes | `string` | `"string"` | — |

## Request body

This operation has no request body.

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `101` | WebSocket protocol switch | `—` | `object` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

Upgrades to the one-shot WebSocket stream authorized by the ticket. For pty and exec sessions, binary messages carry raw stdin/stdout bytes and stdout/stderr are interleaved. postgrip.sandbox.terminal.v1 reserves client-to-agent text frames for strict resize JSON of the form {"type":"resize","rows":24,"columns":80}; postgrip.sandbox.terminal.v2 applies strict JSON control framing in both directions and additionally permits agent-to-client notice messages of the form {"type":"notice","code":"session_ready","message":"Sandbox stream is ready"}. Rows and columns must be integers from 1 through 65535. A zero-length client binary message signals terminal stdin EOF without closing output. Without a negotiated terminal protocol, text messages remain legacy raw stdin. Exec exit codes, and only exec exit codes, use WebSocket close status 4000 plus the process code. For port sessions, postgrip.sandbox.port.v1 carries raw TCP bytes in binary messages; text messages are invalid, and terminal controls and terminal close-code semantics do not apply. Ping/Pong liveness is enforced independently on every proxy hop, and any failed hop terminates both relay peers.

- No additional lifecycle constraint is recorded.

## cURL

Stock cURL is not the conformance runner for this operation: The operation upgrades to WebSocket and is exercised by the protocol runner.

Runner: `websocket-protocol` · Owner: `sdk-maintainers`.

## Protocol adapter

Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.
Use the typed Agent adapter and the `websocket-protocol` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.

## Related operations

- [createSandbox](./createSandbox.md) — Create a sandbox
- [createSandboxSession](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [deleteSandbox](./deleteSandbox.md) — Request sandbox deletion
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes
- [listWorkspaces](./listWorkspaces.md) — List uploaded workspaces

[Back to Agent index](./README.md)
