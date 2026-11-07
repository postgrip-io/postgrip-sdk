# Agent task cancel and optional idempotency keys

## Problem and scope

The Agent API could not stop a task once it was sent, and a task send or a
signal could not be repeated safely after a lost answer. Web adds a
`cancelTask` operation and an optional `Idempotency-Key` on `enqueueTask`,
`signalWorkflow` and `signalWithStartWorkflow`. Web's
[Agent task cancel and idempotency design](https://github.com/postgrip-io/postgrip-web/blob/main/docs/design/agent-task-cancel-and-idempotency-design-20261107.md)
(postgrip-web#2527) owns the server behaviour and the contract. This slice
mirrors that contract, regenerates its derived outputs following the
[contract guide](../development/contracts.md), teaches the generators,
checkers and executors the new `x-postgrip-idempotency: optional` value, and
adds the client methods and the runtime handling below. The Worker and
Service contracts do not change.

| Operation | Go | TypeScript | Python |
| --- | --- | --- | --- |
| `cancelTask` | `Connection.CancelTask`, `TaskClient.Cancel` | `Connection.cancelTask`, `TaskClient.cancel` | `Connection.cancel_task`, `TaskClient.cancel` |

## Design

### D1. Mirror and generation

`contracts/agent-openapi.json` is a byte-for-byte copy of web's
`postgrip-api/agent-openapi.json`. The generators produce the bindings, the
reference pages, the recorded fixtures, the operation inventory and the
coverage report. The bundle digest becomes
`11ab5c645b5ba2b87e37ebdd1dd90abbcbe47b5927a8f68607cd3d1ca5dbfbfe`; the
package READMEs and the production-smoke scenario cite it. TypeScript
publishes `CancelTaskRequest`, `OpenAPICancelTaskRequest`, the
`CancelTask` request and response body types and `IdempotencyOptions` from
`src/agent/index.ts`, recorded in `test/public-surface.json`; Python exports
`CancelTaskRequest` from `postgrip.agent`.

The cancel body is an Agent-plane wire type, so `go/protocol/types.go`
declares it (`protocol.CancelTaskRequest`, `Reason string`
`json:"reason,omitempty"`) and the generator aliases it
(`GO_PROTOCOL_SCHEMAS`). The Go client uses that type; TypeScript and Python
alias the generated contract type.

### D2. `x-postgrip-idempotency: optional`

Web's checker accepts `none`, `optional` and `required`. The generator now
refuses any other value and keeps the annotation in step with the header:
`required` declares a required `Idempotency-Key`, `optional` an optional one,
and `none` none. The inventory schema and checker accept the same three
values, and their self-tests reject an unknown one.

The three executors treat `optional` like `required` except that the key may
be absent:

- A key is sent only when the caller supplies one, and only on an operation
  that declares the header. The SDK never generates a key. It does not
  generate one for `required` operations either: a key the SDK invented could
  not be resent after a process restart, which is the case a key exists for,
  so generating one would promise a safety it does not give.
- A supplied key is checked (1 to 128 visible ASCII characters) before
  sending, as on `required` operations and as the Worker and Service clients
  already check one passed through their generated clients. An invalid key
  fails locally rather than as a server `400 INVALID_IDEMPOTENCY_KEY`.
- The operations are `x-postgrip-retry: bounded`, so with retries enabled a
  keyed send is retried like any keyed mutation and an unkeyed one is sent
  once. No per-operation no-retry status is needed: the server releases the
  key on `408`, `429` and `5xx` answers, before which nothing was kept, and
  keeps it reserved when it could not store an answer.

Go's generated Agent client keeps its method signatures. Its `Do` now accepts
a header the operation declares instead of refusing every header, and the
connection forwards per-call headers only where the operation declares them.

### D3. Passing a key

| | Go | TypeScript | Python |
| --- | --- | --- | --- |
| Task send | `EnqueueInput.IdempotencyKey` | `task.enqueue({ idempotencyKey })` | `task.enqueue(idempotency_key=)` |
| Signal-with-start | `SignalWithStartOptions.IdempotencyKey` | `workflow.signalWithStart(wf, { idempotencyKey })` | `workflow.signal_with_start(idempotency_key=)` |
| Signal | `WorkflowHandle.Signal(client.WithIdempotencyKey(ctx, key), …)` | `connection.signalWorkflow(id, request, { idempotencyKey })` | `handle.signal(name, *args, idempotency_key=)` |
| Connection calls | `client.WithIdempotencyKey(ctx, key)` | `{ idempotencyKey }` options argument | `idempotency_key=` keyword |
| Generated client | `OpenAPI().Do(…, headers, …)` | `openapi.enqueueTask({ headers })` | `openapi.enqueue_task(idempotency_key=)` |

Go's `WithIdempotencyKey` covers the calls whose signatures cannot take an
option (`WorkflowHandle.Signal` is variadic); the option fields are the same
mechanism. TypeScript's `WorkflowHandle.signal` is variadic too, so a keyed
signal goes through `Connection.signalWorkflow`.

### D4. Cancellation reaches the runtimes as a terminal 409

A mutation of a cancelled task by its leasing Agent answers `409
TASK_CANCELLED` with a message that still says the task is terminal. The
TypeScript and Python runtimes already read such a 409 as cancellation:
lease renewal stops, `activity.heartbeat()` raises `CancelledFailure`, and a
refused complete or fail is ignored. Their checks now also accept the code
itself, so a change of message does not hide a cancel.

The Go Worker logged a failed heartbeat and kept going, then logged the
refused complete or fail. It now reads a heartbeat 409 with `TASK_CANCELLED`,
or a message saying the task is terminal or not leased, as a stop: the task
context is cancelled with an internal cause, renewal stops, and nothing is
reported. Any other heartbeat failure is still only logged, so a flaky
connection never stops a task. `activity.Heartbeat` returns
`*failure.Cancelled` for the same answer, as in TypeScript and Python. The
protocol types do not change for this.

The SDK runtimes poll only workflow, activity, query and update tasks, which
`cancelTask` refuses (`TASK_OWNED_BY_WORKFLOW`); the same answer arrives when
a workflow cancel or an activity timeout ends a task, and from a cancelled
standalone task leased by a custom runtime.

### D5. Test and live ownership

`cancelTask` is recorded-tested and cURL-eligible, with
`reverse-dependency` cleanup, owned by the nightly tier: it cancels a `noop`
task the scenario enqueued on a queue no Agent polls. The stage nightly
scenario must add those steps (see the
[live-suites design](live-suites-on-stage-20261017.md), D3). The recorded
fixtures of the three idempotent operations now carry a recorded key.

## Acceptance

- `generate_openapi.py --plane all --check`, the generator unit tests, the
  inventory, fixture, coverage, endpoint, cURL and API documentation checks
  pass.
- Go, TypeScript and Python suites pass, including tests for the cancel route
  and body, `409 TASK_TERMINAL`, a key sent only when given and only where
  declared, an invalid key refused before sending, a keyed send retried with
  the same key and body, `TASK_CANCELLED` read as a terminal mutation, and the
  Go Worker stopping a cancelled task without reporting it.
- Web's discovery gate passes once web pins the merged commit.
