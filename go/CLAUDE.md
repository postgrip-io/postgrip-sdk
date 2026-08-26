# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Unified Go SDK for PostGrip Agent, Worker-management, and Service-management.
It mirrors `../typescript` and `../python`; Agent runtime wire shapes live in
the local `protocol` package. The root `postgrip` package provides the one-token
facade, while direct Agent, Worker, Service, and protocol packages remain
available below the same module.

The module path is `github.com/postgrip-io/postgrip-agent-sdks/go`. Release it from this monorepo with `go/v*` tags; the former `go.postgrip.io/sdk` vanity path is retired.

## Commands

```sh
go test ./...                                  # all tests across all packages
go test ./agent/worker -run TestSleep -v       # single test or pattern in one package
go vet ./...
gofmt -l .                                     # CI fails if non-empty
```

Root CI runs formatting, vet, tests, recorded endpoint conformance, release
artifact inspection, and cross-language drift validation. Keep `GOWORK=off go
test ./...` passing so the published module remains standalone.

## Architecture

### Package DAG (acyclic — keep it that way)

```
agent/failure ─┐
agent/workflow ┼─→ agent/client ─→ agent/worker
agent/activity ┘                  ↑
agent/internal/replay ────────────┘
agent/internal/jsonenv ──→ agent/client, agent/worker

internal/transport ──→ root facade, agent, worker, service
protocol ──→ agent runtime packages
```

The Agent leaves depend only on `protocol`; `agent/client` adds failure and
workflow behavior, and `agent/worker` depends on them. Generated plane clients
depend on their plane transport, never on the root facade. Adding an import
that creates a cycle is a sign the logic belongs at a different layer.

### Interface in `agent/workflow`, implementation in `agent/worker`

`workflow.Context` is the interface customer workflow bodies receive
(`agent/workflow/workflow.go`). It cannot import `agent/client` (would cycle).
The implementation lives in `agent/worker/workflow_context.go`.

When adding a method to the workflow surface, declare it on the interface in
`agent/workflow` and implement it on `workflowContext` in `agent/worker`.

Tests for workflow-context behavior live in `agent/worker`; interface-contract
tests live in `agent/workflow`.

### Workflow execution model

Each leased workflow task goes through:

1. Worker fetches the **full durable history** from the runtime service.
2. `replay.New(history)` builds a cursor walker.
3. A fresh `workflowContext` wraps it; the customer's `workflow.Func` is invoked.
4. Body's calls to `Sleep` / `ExecuteActivity` / `ExecuteChildWorkflow` consult the replay first:
   - History records the command → return persisted result, or `*workflow.Suspended` if still in-flight.
   - History exhausted → enqueue a fresh command and return `*workflow.Suspended`.
   - Body asks for a different command than recorded → `*replay.DeterminismError` → translated to a non-retryable `WorkflowDeterminismViolation` `failure.Application`.

**Suspension is not failure.** When the body returns `*workflow.Suspended`, the Worker calls `BlockTask` (not `FailTask`); the runtime service redelivers when dependencies resolve and the body re-runs from the top with fuller history. **This is the central invariant — workflow bodies must be deterministic and idempotent under re-invocation.** Anything that breaks determinism (random IDs, wall-clock time, map iteration order affecting commands) will surface as a `WorkflowDeterminismViolation` on the next replay.

**`ContinueAsNew` is also modeled as a sentinel error**, not a real failure. `ctx.ContinueAsNew(opts)` returns `*workflow.ContinueAsNewSentinel`; the Worker recognizes it via `errors.As` and translates to a runtime-service `ContinueAsNewResult`. Workflow bodies should `return ctx.ContinueAsNew(...)`.

### Sentinel translation at the SDK boundary

`internal/replay` returns its own private sentinel error types (`ErrCancellationRequested`, `*DeterminismError`). It does **not** know about `failure.Cancelled` or `failure.Application` — that's intentional, so replay stays a leaf and never depends on `failure` (otherwise any code reachable from `failure` could pull in replay).

The boundary translation happens in `worker/workflow_context.go` via `checkReplayCancellation` and `translateReplayError`. **Don't bypass them.** If you add a new replay sentinel kind, add the translation in those two helpers and keep replay's API typed in its own error vocabulary.

### Connection authentication lanes

`agent/client.Connection` handles three contract-owned lanes:

- **Management endpoints** (Task / Workflow / Schedule / namespace CRUD): `Authorization: Bearer <ConnectionOptions.AuthToken>`.
- **Agent endpoints** (`/api/v1/agent/*` and `/api/v1/agents/*/poll`): a delegated refreshable access token injected by the host agent. `ensureAgentSession` runs implicitly before every agent-authenticated request (poll, heartbeat, complete/fail/block, emit-event), refreshing via the stored refresh token as needed. The SDK must not enroll standalone agents.
- **Public bootstrap endpoints**: no management or delegated bearer.

Generated operation metadata selects the lane and signing protocol. Preserve
that separation when changing transport; especially do not send the common
management token to public refresh or delegated runtime routes.

### Activity runtime

Activity helpers (`activity.GetInfo`, `Heartbeat`, `Milestone`) read from a `*activity.Runtime` attached to the activity's `context.Context` via a private context key. The Worker calls `activity.WithRuntime(ctx, runtime)` before invoking the `activity.Func`. The helpers return an error when called outside an activity invocation — the context value isn't there. Don't add globals; new activity-side helpers should follow the same context-key pattern.

### JSON convention: marshal panics on failure

`internal/jsonenv.Marshal` **panics** if `json.Marshal` fails, instead of returning an error. The SDK only marshals types it controls (maps, structs with JSON-safe fields, customer args we treat as opaque), so a marshal failure is a programming error worth surfacing immediately rather than letting a corrupted wire payload propagate. Don't change this to error-returning without auditing every caller.

### Wire-shape re-exports

`client/aliases.go` re-exports the protocol's wire types (`Task`, `WorkflowExecution`, `Schedule`, etc.) so customer code doesn't have to import the protocol module directly. When the protocol adds a new wire type that customer code needs to reference, add the alias here. Don't shadow the protocol type with an SDK-side struct unless you're deliberately diverging the shape — that's almost always wrong (loses the polyglot contract with the TS and Python SDKs).
