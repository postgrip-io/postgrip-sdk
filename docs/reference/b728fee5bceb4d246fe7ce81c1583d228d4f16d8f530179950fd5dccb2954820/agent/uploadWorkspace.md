# Upload a workspace archive

`POST /api/v1/workspaces` · `uploadWorkspace` · Agent

> Contract bundle `b728fee5bceb4d246fe7ce81c1583d228d4f16d8f530179950fd5dccb2954820`
> Agent contract `d9df466806e58ae32ab98f6622086d49749672258af902bdf3777a061fef28ff`

The request body is a raw gzipped tar stream, not a multipart form. Repository and revision metadata travel in the X-PostGrip-Repository and X-PostGrip-Revision headers. Storage is content-addressed, so re-uploading identical bytes returns the existing record rather than creating a new one.

## Operation

| Field | Value |
| --- | --- |
| Plane | `agent` |
| Resource tags | `Sandboxes` |
| Operation class | `tenant-api` |
| Safety | `mutation` |
| Protocol | `archive-stream` |
| Credentials | `postgrip-token` |
| Required scopes | `[["agent:operate"]]` |
| Idempotency | `none` |
| Retry | `none` |
| Pagination | `none` |

## Parameters

| Name | In | Required | Schema | Example | Description |
| --- | --- | --- | --- | --- | --- |
| `X-PostGrip-Repository` | header | no | `string` | `"my-repo"` | — |
| `X-PostGrip-Revision` | header | no | `string` | `"9f1c2d4"` | — |

## Request body

Content type: `application/gzip` · Schema: `string (binary)`

```json
"string"
```

## Responses

| Status | Meaning | Content type | Schema |
| --- | --- | --- | --- |
| `201` | Content-addressed workspace | `application/json` | `SandboxWorkspace` |
| `default` | Request failed | `application/json` | `ErrorResponse` |

Illustrative success body:

```json
{
  "createdAt": "2026-01-01T00:00:00Z",
  "createdBy": "string",
  "expiresAt": "2026-01-01T00:00:00Z",
  "id": "string",
  "repositoryName": "string",
  "sha256": "string",
  "sizeBytes": 1,
  "tenantId": "string"
}
```

Errors use the stable JSON envelope `code`, `message`, `requestId`, and optional `details`.
The `requestId` is safe to include in support and audit workflows; never log the bearer token.

## Behavior and lifecycle

The request body is a raw gzipped tar stream, not a multipart form. Repository and revision metadata travel in the X-PostGrip-Repository and X-PostGrip-Revision headers. Storage is content-addressed, so re-uploading identical bytes returns the existing record rather than creating a new one.

- Use isolated fixtures and clean up recorded resource identifiers.

## cURL

Stock cURL is not the conformance runner for this operation: The operation transfers a stream or archive and is exercised by the streaming runner.

Runner: `streaming-protocol` · Owner: `sdk-maintainers`.

## Protocol adapter

Raw language snippets are intentionally omitted because an unsigned, unframed, or non-streaming HTTP example would be incorrect.
Use the typed Agent adapter and the `streaming-protocol` conformance runner; it owns signing, streaming, archive, long-poll, or WebSocket semantics for this operation.

## Related operations

- [connectSandboxSession](./connectSandboxSession.md) — Attach to an interactive session over WebSocket
- [createSandbox](./createSandbox.md) — Create a sandbox
- [createSandboxSession](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [deleteSandbox](./deleteSandbox.md) — Request sandbox deletion
- [deleteWorkspace](./deleteWorkspace.md) — Delete an uploaded workspace
- [getSandbox](./getSandbox.md) — Fetch a sandbox
- [getWorkspace](./getWorkspace.md) — Fetch an uploaded workspace
- [listSandboxes](./listSandboxes.md) — List sandboxes

[Back to Agent index](./README.md)
