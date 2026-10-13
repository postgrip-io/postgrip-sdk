# Agent module ownership

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

[Architecture](../development/architecture.md) separates pure models,
orchestration and external adapters, with composition at the public entry
point. The SDK architecture audit of `main` at `3675b2f2` found Agent modules
that mix those roles:

- **Concrete adapters as dependencies (A09).** Go `TaskClient`,
  `WorkflowClient`, `ScheduleClient` and `SandboxClient` hold `*Connection`, and
  the Go runtime (`worker.Options`, `workflowContext`) consumes it too.
  TypeScript `ClientOptions`, the subclients, handles, `SandboxClient` and
  `Agent` require the `Connection` class, including its private transport and
  auth state. Python types its clients and runtime against `Connection`, and
  `agent.py:_connection_from_client` dispatches with `isinstance`.
- **Mixed modules (A10, Agent part).** Python `agent/client.py` holds the HTTP,
  signing and session adapter (`Connection`) beside client orchestration and
  pure metadata transformations. TypeScript `agent/client.ts` mixes composition,
  orchestration and pure memo and description transformations, and
  `connection.ts` combines JSON transport, session management, history paging
  and archive upload. Go `Connection` owns task-kind selection and multi-page
  history walking beside HTTP.
- **Sandbox (A11).** TypeScript `sandbox.ts` holds pure relay and status
  transformations, `waitUntilRunning` orchestration, `SandboxClient` and the raw
  WebSocket `SandboxSession`. Python `sandbox.py` holds readiness polling, upload
  HTTP and the WebSocket session. It also imports `has_authorization_header` from
  `client.py`, while `Client` imports `SandboxClient` lazily, which is a source
  cycle hidden by import timing. Go already splits `sandbox_client.go` and
  `sandbox_session.go`.

The [contract-driven layering design](contract-driven-sdk-layering.md) owns the
shared executor, generated operations over an executor interface (A08), and
the Worker and Service transport consolidation (A10, management part). This
design covers the Agent module boundaries it leaves. Every slice preserves
behavior, public names, import paths and request bytes. Contracts, wire types,
runtime semantics and the replay engine (designed separately in PR #72) do not
change here.
Follow [architecture](../development/architecture.md) and
[validation](../development/testing.md).

## Design

### Capability interfaces

Orchestration depends on capability-sized contracts declared where they are
consumed, never on a concrete adapter class:

| Capability | Operations |
| --- | --- |
| Task operations | enqueue, get, list, task events (page and walk) |
| Workflow operations | get, list, count, history (page and walk), signal, signal-with-start, cancel, terminate |
| Schedule operations | create, get, list, update, delete, pause, unpause, trigger, backfill |
| Sandbox operations | sandbox and workspace lifecycle, session creation, archive upload |
| Runtime operations | poll, heartbeat, complete, fail, block, append event, agent auth configuration |

- **Go.** Unexported interfaces in `agent/client` (for example `taskOps`) are
  satisfied by `*Connection`. The client structs hold those interfaces.
  `worker.Options.Connection` stays `*client.Connection` for compatibility, and
  `worker` declares its own runtime interface that the worker and
  `workflowContext` use internally.
- **TypeScript.** Exported `interface` types in `agent/_ports.ts`. The
  `ClientOptions.connection`, subclient, handle, `SandboxClient` and `Agent`
  parameter types widen from `Connection` to the interface they use.
  `Connection` satisfies them structurally, so existing callers compile
  unchanged. The interfaces are public types, because the widened parameters
  name them, and they are added deliberately to the recorded public surface.
- **Python.** `typing.Protocol` classes in `agent/_ports.py`. Clients and the
  runtime annotate their dependencies with them. `_connection_from_client`
  accepts any object with a `connection` attribute or the runtime protocol
  instead of checking `isinstance(..., Client | Connection)`, and keeps the
  same error for neither.

Root and plane constructors keep composing the concrete `Connection`.

### Module splits

Each split moves code without changing it, apart from imports. The old module
re-exports every public name it previously defined, so import paths keep
working:

- **Python Agent client.** `agent/_connection.py` takes the `Connection`
  adapter: HTTP, signing, session and the opener. `agent/_workflow_models.py`
  takes the pure memo, UI, description and option normalizers. `agent/client.py`
  keeps client orchestration and re-exports `Connection`,
  `has_authorization_header` and `urlopen`, which existing tests patch.
- **Python neutral header helper.** `has_authorization_header` moves to
  `_internal/http.py`. `sandbox.py` imports it from there, which removes its
  dependency on `client.py`. `client.py` then imports `SandboxClient` at module
  top, with no cycle.
- **Python sandbox.** `agent/_sandbox_session.py` takes the WebSocket session
  and its factory, and `sandbox.py` keeps `SandboxClient`, readiness
  orchestration and pure helpers, re-exporting `SandboxSession`.
- **TypeScript sandbox.** `agent/_sandbox_session.ts` takes `SandboxSession`
  and its WebSocket factory, and `agent/_sandbox_relay.ts` takes the pure relay
  URL, exit-code and input transformations. `sandbox.ts` keeps `SandboxClient`
  and `waitUntilRunning`, re-exporting the moved public names.
- **TypeScript Agent client.** `agent/_workflow_models.ts` takes the pure memo
  and description transformations. `agent/_history.ts` takes history paging,
  and `agent/_archive_upload.ts` takes the archive upload adapter used by the
  connection.
- **Go Agent.** Task-kind selection and multi-page walking move from
  `Connection` methods into the clients that orchestrate them. The `Connection`
  methods stay as thin compatibility wrappers.

Underscore-prefixed modules are internal and not exported from package entries,
except for the deliberate port interfaces noted above.

## Compatibility

No behavior, request, error or published import path changes. The TypeScript
public surface gains the port interface types, recorded in
`typescript/test/public-surface.json`. Python adds no names to
`postgrip.agent`. Go adds no exported names.

## Delivery slices

1. **Python header and cycle.** Move `has_authorization_header`, remove the
   sandbox back-dependency, and import `SandboxClient` eagerly.
2. **Python sandbox split.**
3. **TypeScript sandbox split.**
4. **Python Agent client split.**
5. **TypeScript Agent client split.**
6. **Capability interfaces**, one PR per language (Go, TypeScript, Python),
   including the Go task-kind and paging move.

Each slice is its own PR under the [review process](../development/contributing.md).
A slice that changes an owner's description of module ownership updates the
architecture guide in the same PR.

## Acceptance

- Existing language suites, recorded endpoint and cURL runners, the TypeScript
  public-surface test and the package-boundary tests pass unchanged, apart from
  the intended surface additions in slice 6.
- Every previously public name still imports from its previous module.
- Python: a test imports `postgrip.agent.sandbox` in a fresh interpreter without
  importing `postgrip.agent.client`, proving that the cycle is gone.
- Each capability-interface slice adds a test that drives a client or the runtime
  through a minimal fake implementing only the interface, with no `Connection`.
