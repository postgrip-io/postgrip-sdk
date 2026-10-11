# SDK boundaries

`go/`, `typescript/` and `python/` each publish one artifact with Agent, Worker
management and Service management namespaces. Root facades configure these
clients; direct plane imports remain usable independently. Generated clients
must not depend on the root facade. Shared transport helpers belong in the
language's internal infrastructure and must preserve each plane's policy.

Wire ownership and compatibility are defined in [contracts](contracts.md).
Authentication and endpoint configuration are owned by [authentication](../authentication.md)
and [configuration](../configuration.md). Never route a common management token
to a delegated runtime or public refresh endpoint.

## Runtime responsibilities

Agent clients submit or inspect tasks, workflows and schedules. A host-launched
managed runtime owns polling, leases, refresh, signing and workflow/activity
execution. SDKs do not enroll standalone host agents. Worker management is a
separate namespace; an Agent polling worker is not a Worker-management client.

Go's `agent/workflow.Context` is the customer interface; its implementation
belongs in `agent/worker`. Keep replay infrastructure independent of SDK failure
types and translate replay cancellation/determinism errors at the worker boundary.
Workflow suspension blocks the task; it must not become a task failure.
Activity runtime context is per invocation, never global.

Language-specific runtime semantics and examples have one owner each:

- [Go runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/go/agent/docs/workflow-runtime.md)
  and [package responsibilities](https://github.com/postgrip-io/postgrip-sdk/blob/main/go/agent/docs/packages.md).
- [TypeScript runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/typescript/docs/workflow-runtime.md).
- [Python runtime](https://github.com/postgrip-io/postgrip-sdk/blob/main/python/docs/workflow-runtime.md).

Preserve deterministic replay, continuation/cancellation semantics and public
exports when refactoring. Sandbox checks are limited static checks, not an
isolation guarantee. No removal of a published API based only on absent local
callers. JSON conversion and signing changes need compatibility evidence.

## Style and public surface

Use `gofmt`, idiomatic exported Go comments, two-space TypeScript with explicit
named exports, and four-space Python following PEP 8. Keep TypeScript ESM
subpaths and Python exports deliberate. Do not create a fourth publishable
manifest or plane-specific release path; [releasing](../releasing.md) owns tags
and version coordination.
