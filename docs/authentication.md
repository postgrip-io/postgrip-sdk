# Authentication

PostGrip SDK applications configure one opaque tenant-management bearer:

```sh
export POSTGRIP_TOKEN="pgt_..."
```

The root client sends that same token to Agent management, Worker management,
and Service management routes. Authorization remains endpoint-scoped: the
server resolves the token to one tenant, checks expiry and revocation, then
requires one of the concrete scope alternatives declared by the operation.
The generated reference prints those alternatives exactly.

Typical scopes include Agent read or operate authority, Worker read or operate
authority, and Service read, deploy, operate, or administration authority. A
single token may receive scopes across all three planes. Applications that
need a smaller blast radius should issue multiple tokens and construct
separate root clients.

## Runtime credentials are different

A host PostGrip Agent launches managed workflow runtimes with short-lived
Agent access and refresh tokens plus an ephemeral signing key. Those values
are injected as `POSTGRIP_AGENT_*` variables, remain bound to the delegated
namespace and queues, and authenticate only the Agent operations that declare
delegated sessions as an accepted credential. Some task routes accept either credential class;
runtime task types remain constrained to the delegated namespace/queues.
Signing is required where the operation declares it, not on every Agent read.
They must not be copied into `POSTGRIP_TOKEN` or sent to Worker and Service
management routes.

## Failure behavior

Authentication and authorization failures use the common error envelope:

```json
{
  "code": "INSUFFICIENT_SCOPE",
  "message": "the token does not grant this operation",
  "requestId": "req_...",
  "details": {}
}
```

Treat the token as a secret but the request ID as diagnostic metadata. Never
log authorization headers. Rotate or revoke a token that may have entered a
log, trace, crash report, shell history, URL, or process argument list.

Go Agent HTTP failures omit server response content from their default error
text. The typed `SDKError.ResponseBody` retains the original body for explicit
inspection and may contain reflected credentials or other secrets. Review and
redact it before logging; arbitrary server error messages are not safe log data.

## Untrusted clients

`POSTGRIP_TOKEN` is intended for trusted server-side processes and automation.
Browsers, mobile apps, desktop clients, and public AI-agent frontends require a
delegated or user-facing authentication flow and must not embed a management
token in shipped code.
