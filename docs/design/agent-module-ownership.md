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
| Runtime operations | health, poll, heartbeat, complete, fail, block, append event, agent auth configuration, workflow history and task pages, workflow execution and task lookup, and enqueue for the commands workflows schedule |

- **Go.** Unexported interfaces in `agent/client` (for example `taskOps`) are
  satisfied by `*Connection`. The client structs hold those interfaces.
  `worker.Options.Connection` stays `*client.Connection` for compatibility, and
  `worker` declares its own runtime interface that the worker and
  `workflowContext` use internally. The exported
  `WaitForTaskCompletion(ctx, *Connection, …)` keeps its signature and wraps an
  unexported helper that takes the task interface; clients call the helper.
- **TypeScript.** Internal `interface` types in `agent/_ports.ts`. Exported
  option properties such as `ClientOptions.connection` and
  `AgentOptions.connection`, and public fields, keep the `Connection` type, so
  code that reads them keeps compiling. Inside each class, the dependency is
  stored in a private field typed as the port it uses, and every method body
  goes through that field. The compiler therefore proves the class uses nothing
  beyond the port. No port is exported, and the public surface is unchanged.
- **Python.** `typing.Protocol` classes in `agent/_ports.py`. Public attribute
  annotations, such as `WorkflowHandle.connection`, keep `Connection`.
  Orchestration code holds and calls its dependency through the protocol type.
  `_connection_from_client` accepts any object with a `connection` attribute,
  or one satisfying the runtime protocol, instead of checking
  `isinstance(..., Client | Connection)`, and keeps the same error for neither.

Root and plane constructors keep composing the concrete `Connection`.

### Module splits

Each split moves code without changing it, apart from imports. The old module
re-exports every public name it previously defined, so import paths keep
working. It also re-exports the private helpers that existing tests import from
it: `_parse_timestamp` from `postgrip.agent.client`, and
`_same_origin_websocket_connection_factory` from `postgrip.agent.sandbox`.

- **Python Agent client.** `agent/_connection.py` takes the `Connection`
  adapter: HTTP, signing, session and the opener. Multi-page history walking,
  `_iter_history_pages` and its use in `iter_task_events` and
  `iter_workflow_history`, moves to `agent/_history.py`, used by the clients and
  handles. `Connection` keeps those two methods as thin wrappers over it.
  `agent/_workflow_models.py` takes the pure memo, UI, description and option
  normalizers. `agent/client.py` keeps client orchestration and re-exports
  `Connection` and `has_authorization_header` for import compatibility.

  Requests resolve `urlopen` in the module that defines them, so a re-export
  is not a patch point. `postgrip.agent.client.urlopen` is not public API. The
  slice moves the request-opener patch point to `postgrip.agent._connection.urlopen`,
  and updates the tests that patched the old name in the same PR. That is the
  only test change the split allows.
- **Python neutral header helper.** `has_authorization_header` moves to
  `_internal/http.py`. `sandbox.py` imports it from there, and imports the
  `Connection` type from `_connection.py`, which removes its dependency on
  `client.py`. `client.py` then imports `SandboxClient` at module top, with no
  cycle. This needs `_connection.py` to exist, so the cycle fix ships together
  with the `Connection` extraction.
- **Python sandbox.** `agent/_sandbox_transport.py` takes the external
  adapters: the WebSocket session and its factory, and the workspace upload
  HTTP request that `SandboxClient.upload_workspace` builds and opens today.
  `agent/_sandbox_models.py` takes the pure helpers: relay URL, exit code,
  readiness test and ID validation. `sandbox.py` keeps `SandboxClient` and its
  readiness orchestration, which coordinate those modules, and re-exports every
  moved public name. The sandbox's upload patch point moves with the request,
  as for the client.
- **TypeScript sandbox.** `agent/_sandbox_session.ts` takes `SandboxSession`,
  its WebSocket factory and an `openSandboxSession` adapter operation. That
  operation performs the dial, sets `binaryType`, attaches the transport open
  and error listeners, and returns the session. `agent/_sandbox_relay.ts` takes
  the pure relay URL, exit-code and input transformations. `sandbox.ts` keeps
  `SandboxClient` and `waitUntilRunning`, which only coordinate ticket creation
  with that adapter, and re-exports the moved public names.
- **TypeScript Agent client.** `agent/_workflow_models.ts` takes the pure memo
  and description transformations. `agent/_history.ts` takes history paging,
  and `agent/_archive_upload.ts` takes the archive upload adapter used by the
  connection.
- **Go Agent.** Task-kind selection and multi-page walking move from
  `Connection` methods into the clients that orchestrate them. The `Connection`
  methods stay as thin compatibility wrappers. The sandbox relay dial
  (`dialSandboxRelay`, which reads the connection's private transport settings
  and calls `websocket.Dial`) becomes a `Connection` adapter operation exposed
  through the sandbox interface, so `SandboxClient` needs no concrete
  connection state.
- **Runtime history walking.** The Agent runtimes (Go `worker/dispatch.go`,
  TypeScript `agent.ts`, Python `agent.py`) fetch whole workflow histories
  today through the adapter's full-history methods. They instead walk pages
  through the runtime port's page operation with each language's shared history
  walker. The adapter's full-history methods remain only for external
  compatibility.

Underscore-prefixed modules are internal and not exported from package entries.

## Compatibility

No behavior, request, error or published import path changes, and no public
type changes. The TypeScript public surface, the names Python exports from
`postgrip.agent` and Go's exported API are unchanged. The only change outside
the moved code is the private Python request-opener patch point, which moves to
the adapter module with the requests that use it.

## Delivery slices

1. **Python connection and cycle.** Extract `Connection` to `_connection.py`
   with the opener and patch point, move `has_authorization_header`, remove the
   sandbox back-dependency, and import `SandboxClient` eagerly.
2. **Python sandbox split.**
3. **TypeScript sandbox split.**
4. **Python Agent client split:** history walking and pure workflow models.
5. **TypeScript Agent client split.**
6. **Capability interfaces**, one PR per language (Go, TypeScript, Python),
   including the Go task-kind, paging and relay-dial moves and runtime history
   walking.

Each slice is its own PR under the [review process](../development/contributing.md).
A slice that changes an owner's description of module ownership updates the
architecture guide in the same PR.

## Acceptance

- Existing language suites, recorded endpoint and cURL runners, the TypeScript
  public-surface test and the package-boundary tests pass unchanged. The only
  exception is updating Python patch targets to the moved opener.
- Every previously public name still imports from its previous module.
- Python: importing a submodule always runs the package initializer, which
  imports `client.py`, so a fresh-import test cannot prove the cycle is gone. A
  static test parses `sandbox.py` and the moved sandbox modules and fails if any
  of them imports `postgrip.agent.client`, even under `TYPE_CHECKING`. A second
  test asserts that `client.py` imports the sandbox module at top level.
- Each capability-interface slice converts every consumer the design names. For
  Go these are `TaskClient`, `WorkflowClient`, `WorkflowHandle`,
  `ScheduleClient`, `SandboxClient`, the worker and `workflowContext`; TypeScript
  and Python have the corresponding clients, handles, `SandboxClient` and
  `Agent`. For each consumer, the slice adds a minimal-fake test driving it
  through only its port. Each consumer's stored dependency is also asserted to
  be the port type: a Go compile-time field type assertion, the TypeScript
  private field type, or a Python test over the annotations. In TypeScript, the
  fake is cast at the unchanged public parameter type; the class's private port
  field proves the narrower dependency at compile time.
