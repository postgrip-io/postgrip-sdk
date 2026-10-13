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

### Credential selection and current limits

On Agent operations whose contract accepts either credential class, an Agent
connection with runtime access/refresh credentials selects the delegated lane.
Go and Python Agent connections read those credentials from the process
environment, including when constructed by a root facade. TypeScript
connections accept explicit `agentAuth` configuration; a managed Agent runtime
configures its connection. A root management token therefore does not by itself
prove that every Agent call uses the management lane. Keep management-only
applications separate from host-injected runtime environments.

Public operations must receive no bearer credential. The Go Agent connection
runs through the shared executor, which removes any `Authorization` header from
a public request, in any spelling, including one configured through
`ConnectionOptions.Headers`. The TypeScript and Python Agent adapters still copy
caller-supplied headers before applying the auth lane, so there an explicit
`Authorization` header can reach public session refresh. Use the token options,
not a custom authorization header. That remaining gap is against the
[architecture boundary](development/architecture.md), not permission to weaken
it; the [layering design](design/contract-driven-sdk-layering.md) moves those
adapters onto the executor.

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
text. For ordinary JSON operations, the typed `SDKError` carries the decoded
envelope's `Code`, `RequestID` and `Details`. Workspace-upload failures do not
decode the envelope, so those fields stay empty there. `ResponseBody` retains
the original body for explicit inspection in both cases. These fields are server-provided and may contain reflected
credentials or other secrets. Review and redact them before logging; arbitrary
server error content is not safe log data.

TypeScript Agent HTTP failures, including workspace uploads, raise
`AgentAPIError`, a `PostGripAPIError` like `WorkerAPIError` and
`ServiceAPIError`. Its text names only the method, route, status and standard
status text. `code`, `requestId` and `details` come from the decoded envelope,
and `responseBody` retains the original body; like Go's fields they are
server-provided, so review and redact them before logging. A response body that
is not valid JSON fails with a message naming the request, without the body.

Python Agent HTTP failures currently use ordinary `RuntimeError` paths and can
include server-provided text. The exported `PostGripAgentError` bases in
TypeScript and Python cover workflow/activity failure types, not transport
failures. Do not infer Go's and TypeScript's default error-text protection for
Python; review and redact diagnostic content before logging it.

## Untrusted clients

`POSTGRIP_TOKEN` is intended for trusted server-side processes and automation.
Browsers, mobile apps, desktop clients, and public AI-agent frontends require a
delegated or user-facing authentication flow and must not embed a management
token in shipped code.
