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

The Agent workflow runtime (`agent.py`) keeps its own lifecycle and is outside
this slice.

### TypeScript Agent

Thread the caller's `AbortSignal` through every request `watchEvents` makes:

- `Connection.getTask(taskId, options?: { signal?: AbortSignal })` and
  `Connection.getWorkflow(workflowId, options?)`, the latter used when
  `watchEvents` first resolves the handle's task ID;
- `HistoryPageOptions.signal`, forwarded by `getTaskEventsPage` to the
  generated operation for every page;
- `iterateTaskEvents(taskId, options?)` and `getTaskEvents(taskId, options?)`,
  passing the signal to each page fetch.

`watchTaskEvents` passes `options.signal` to both calls and waits with
`abortableDelay` from `src/internal/polling.ts`. When the caller's signal is
aborted, the generator returns without yielding further events and without
throwing, which is how it ends at the loop check today. Errors that are not
caused by that signal still propagate. The new parameters are optional, so
existing callers compile and behave as before.

## Compatibility

No public name is removed, and no request bytes change. These changes are
observable:

- Cancelling a Python Agent `async` call closes its active request instead of
  letting it finish in a background thread. Cancelling `result()` stops
  polling.
- Aborting a TypeScript `watchEvents` signal ends the iterator promptly during
  a pending request or delay.
- TypeScript `getTask`, `getWorkflow`, `getTaskEvents`, `iterateTaskEvents`
  and `getTaskEventsPage` accept an optional signal.

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
  same holds for `result()` with no timeout and for another Agent `async`
  method. Same-origin redirects are still followed, and cross-origin ones still
  refused.
- TypeScript: aborting while the task-ID lookup, `getTaskEvents` or `getTask`
  is pending, and while the poll delay is pending, settles `next()` with `done: true` without waiting
  for the request or delay. The aborted request receives the signal. An error
  not caused by the abort still rejects.
- Existing Agent tests in both languages pass.
