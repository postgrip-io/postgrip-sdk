# Agent request cancellation

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

The SDK architecture audit of `main` at `3675b2f2` found two Agent client paths
where cancellation stops at the public API instead of reaching the request:

- **Python.** `WorkflowHandle.result()` hands the whole `result_sync` polling
  loop to `asyncio.to_thread`. Cancelling the coroutine leaves the thread
  polling `get_task`, and with the default `timeout=None` it polls until the
  workflow finishes. Every other Agent `async` method also wraps synchronous
  I/O in `asyncio.to_thread` without a way to stop the active request. Worker
  and Service already stop theirs: their `_run` helpers set a cancellation
  event that closes the active socket.
- **TypeScript.** `watchTaskEvents` checks `signal.aborted` only at the top of
  its loop. `getTaskEvents` and `getTask` receive no signal, and the delay
  between polls uses a plain `setTimeout`. An abort while a request or delay is
  pending leaves `next()` blocked until that work finishes.

Python's cancellation mechanism is copied byte for byte into
`python/src/postgrip/worker/client.py` and `python/src/postgrip/service/client.py`:
the `_RequestCancelled` sentinel, the cancellation-aware connection and handler
classes, and a per-plane `ContextVar` holding the event. An Agent fix should
reuse one copy rather than add a third.

This design covers request cancellation on these paths only. Contracts, wire
types, retry, timeout and redirect policy, error types, and the Agent workflow
runtime's polling loop do not change. The shared executor in the
contract-driven layering design (PR #69) builds on the Python mechanism
extracted here. Follow [architecture](../development/architecture.md) and
[validation](../development/testing.md).

## Design

### Python shared cancellation

Move the cancellation event context, `_RequestCancelled`, the
cancellation-aware HTTP and HTTPS connection and handler classes, and a
`run_cancellable(callback, *args, **kwargs)` coroutine into
`python/src/postgrip/_internal/http.py`. That module already owns neutral HTTP
mechanics. `run_cancellable` sets a fresh event in the context, runs the callback
with `asyncio.to_thread`, and sets the event if the awaiting task is cancelled,
as Worker and Service `_run` do today.

Worker and Service import these names and delete their copies. Each plane keeps
its own redirect handler (`_NoRedirect`), handler order, opener composition,
retry loop and the `_RequestCancelled` handling inside it. One shared context
variable replaces the two per-plane ones. The event is only read inside the
thread that `run_cancellable` starts, so planes cannot observe each other's
events.

### Python Agent

The Agent `Connection` opener composes the shared cancellation-aware handlers
with the existing same-origin `SafeRedirectHandler`, and keeps its 30-second
timeout and bounded reads. Agent `async` methods in `client.py` call
`run_cancellable` instead of `asyncio.to_thread`. Cancelling one closes its
active socket, and `asyncio.CancelledError` propagates to the caller as it does
today. Synchronous `*_sync` methods are unchanged.

`WorkflowHandle.result()` becomes a native `async` loop that shares its
decision logic with `result_sync`: follow continue-as-new, re-resolve a failed
task to the workflow's current run, return a value or raise `TaskFailedError`
or `TimeoutFailure`. Each `get_task` and `get_workflow` call goes through
`run_cancellable`, and the wait between polls uses `asyncio.sleep`. Cancelling
`result()` therefore stops both the active request and the loop. `result_sync`
keeps its current blocking behavior. `watch_events` likewise awaits each request
through `run_cancellable`.

`events()` and `watch_events()` resolve a missing task ID by calling
`describe_sync()` directly, which blocks the event loop and cannot be
cancelled. Both instead resolve it through `run_cancellable`, as `describe()`
does with `asyncio.to_thread` today.

The Agent workflow runtime (`agent.py`) keeps its own lifecycle and is outside
this slice.

### TypeScript Agent

Thread the caller's `AbortSignal` through every request `watchEvents` makes:

- `Connection.getTask(taskId, options?: { signal?: AbortSignal })` and
  `Connection.getWorkflow(workflowId, options?)`, the latter used when
  `watchEvents` first resolves the handle's task ID;
- `HistoryPageOptions.signal`, forwarded to the generated operation by every
  method that accepts that type: `getTaskEventsPage` and
  `getWorkflowHistoryPage`;
- `iterateTaskEvents(taskId, options?)` and `getTaskEvents(taskId, options?)`,
  passing the signal to each page fetch.

The shared history page iterator checks the signal before fetching each page and
before yielding each item. When the signal is aborted it throws the signal's
reason, as `followPages` does and as an aborted page fetch already does. A
direct `iterateTaskEvents` consumer that aborts after one event therefore
receives no further buffered event, and `getTaskEvents` rejects.

`watchTaskEvents` passes `options.signal` to both calls and waits with
`abortableDelay` from `src/internal/polling.ts`. It also checks the signal
before yielding each event, so a consumer that aborts between two `next()`
calls receives no further buffered event. When the caller's signal is aborted,
including an abort the page iterator or a request reports, the generator
returns without yielding further events and without throwing, which is how it
ends at the loop check today. Errors that are not caused by
that signal still propagate.

These reads can first wait on a delegated-session refresh. `ensureAgentSession`
shares one in-flight `refreshAgentSession` among all concurrent callers. A
signaled request races its wait on that shared refresh against its own signal.
On abort the caller stops waiting and the request is abandoned, but the shared
refresh is not cancelled, because other requests depend on it. Its result is
stored for later callers as it is today. The new parameters are optional, so
existing callers compile and behave as before.

## Compatibility

No public name is removed, and no request bytes change. These changes are
observable:

- Cancelling a Python Agent `async` call closes its active request instead of
  letting it finish in a background thread. Cancelling `result()` stops
  polling. `events()` and `watch_events()` no longer block the event loop while
  resolving a task ID.
- Aborting a TypeScript `watchEvents` signal ends the iterator promptly during
  a pending request or delay.
- TypeScript `getTask`, `getWorkflow`, `getTaskEvents`, `iterateTaskEvents`,
  `getTaskEventsPage` and `getWorkflowHistoryPage` accept an optional signal.
  Aborting it during `iterateTaskEvents` throws the signal's reason.

## Delivery slices

Each slice is its own PR under the [review process](../development/contributing.md).

1. **Python extraction.** Move the shared cancellation mechanism into
   `_internal/http.py` and switch Worker and Service to it, with no behavior
   change.
2. **Python Agent.** Make the Agent opener cancellation-aware, route its
   `async` methods through `run_cancellable`, and make `result()` a native
   `async` loop.
3. **TypeScript Agent.** Thread `AbortSignal` through `watchEvents` and the
   task and workflow read methods.

## Acceptance

- Python: existing Worker and Service cancellation tests pass unchanged after
  slice 1.
- Python: against a local server that holds a `get_task` response, cancelling
  `result()` closes the held connection, and no further request arrives. The
  same holds for `result()` with no timeout, for another Agent `async` method,
  and for the task-ID lookup in `events()` and `watch_events()` on a handle
  from `get_workflow_handle()`. Same-origin redirects are still followed, and cross-origin ones still
  refused.
- TypeScript: aborting while the task-ID lookup, a shared session refresh,
  `getTaskEvents` or `getTask` is pending, and while the poll delay is pending, settles `next()` with `done: true` without waiting
  for the request or delay. The aborted request receives the signal, and an
  aborted refresh wait leaves the shared refresh to complete for another
  caller. Aborting between two `next()` calls while a page still holds
  unyielded events yields none of them, both through `watchEvents` and through
  a direct `iterateTaskEvents` loop, which throws the signal's reason. A signal
  passed to `getWorkflowHistoryPage` reaches its request. An error not caused by
  the abort still rejects.
- Existing Agent tests in both languages pass.
