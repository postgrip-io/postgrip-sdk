# Deterministic workflow replay across languages

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

The SDK architecture audit of `main` at `3675b2f2` found that the three Agent
runtimes do not replay durable history the same way. Go's
`go/agent/internal/replay` is closest to the intended behavior; the TypeScript
and Python runtimes diverge from it, and every language reads wall time somewhere
it promises logical time:

- **Logical time.** Go `workflow.Context.Now()` promises time that is durable
  across replays, but `newWorkflowContext` reads `time.Now()`. Python
  `workflow.now()` reads `datetime.now(timezone.utc)`. The TypeScript guide tells
  users to call `workflowInfo().now`, which does not exist. The same history can
  take a different time-dependent branch after redelivery.
- **Command order.** TypeScript and Python keep one cursor per command kind and
  never compare positions across kinds. A workflow that now runs `Timer(1000)`
  before `Activity(A)` against history `Activity(A), Timer(1000)` reuses both
  results instead of failing. Go rejects it in `checkCommandOrder`.
- **Update position.** TypeScript and Python run every completed update as soon
  as its handler is registered, before earlier commands are replayed, and ignore
  `WorkflowUpdateAccepted`. Their update tasks replay the whole workflow in query
  mode and only then call the handler, so a handler cannot issue commands. Go
  applies each update at its accepted position (`NextUpdateBeforeCommand` and
  `ConsumeUpdate`).
- **Replay introspection.** Python `workflow.unsafe.is_replaying()` and
  `is_replaying_history_events()` always return `False`.
- **Ownership.** `WorkflowReplay` lives in `typescript/src/agent/agent.ts` and
  `python/src/postgrip/agent/agent.py` beside polling and dispatch, and builds
  `ApplicationFailure` itself. Its failure type is `DeterminismViolation`, while
  Go and all three language guides use `WorkflowDeterminismViolation`.

This design changes only how the Agent runtimes replay history they already
fetch. Contracts, wire types, the runtime service, history event shapes, signal
delivery, activity and child resolution through live task state, and Agent
transport do not change. Follow [architecture](../development/architecture.md),
[contracts](../development/contracts.md) and [validation](../development/testing.md).

## Replay semantics

Go's replay engine is the reference. Every language implements the following
over the history returned by `getWorkflowHistory`, in history order.

### Ordered command cursor

Command events are `ActivityTaskScheduled`, `TimerStarted` and
`ChildWorkflowExecutionStarted`. When workflow code issues a command of kind K:

1. If no unconsumed event of kind K remains, the command is new: the runtime
   schedules it, or stops replay in query and update replay.
2. Otherwise take the next unconsumed event of kind K. If an unconsumed command
   event of another kind has a lower history index, fail with a determinism
   error naming the recorded and requested kinds.
3. Compare recorded identity: `activity_type`, `workflow_type`, or
   `duration_ms` for timers. A mismatch is a determinism error.

An activity retry consumes the retry attempt's `ActivityTaskScheduled` event
under the same rule. Query, update and workflow replay use the same cursor.

### Update boundaries

Build an ordered update list from `WorkflowUpdateAccepted` events. Matching
`WorkflowUpdateCompleted` and `WorkflowUpdateFailed` events, by `task_id`, mark
an entry completed or failed. A completion or failure event without an accepted
event is a legacy entry positioned at its own index.

The next update boundary applies only when its index precedes the next
unconsumed command event, or when no command events remain:

- **Before each durable command** (strict). A failed entry is consumed without
  running a handler. A completed entry runs its registered handler with the
  recorded `args`. A missing handler is a determinism error. A pending entry
  suspends the workflow task until the update finishes.
- **After each durable command and on handler registration** (deferred). Apply
  boundaries the same way, but stop without error at a missing handler or a
  pending entry, so later registration can reach it.

Commands issued by a replayed update handler consume the history that follows
its boundary. Signals keep their current behavior: every recorded signal is
delivered when its handler is registered.

An update task replays its source workflow in replay-only mode until replay
stops at this task's pending boundary. It then consumes that boundary and runs
the handler live with the update task's ID. Commands the handler issues are
scheduled with that ID as `workflowTaskId`, so their completion wakes the update
task, and a suspension blocks the update task. Query tasks replay the same way
and stop at the first new command or pending boundary.

### Logical clock

Replay state owns the workflow clock:

1. It starts at `created_at` of the first `WorkflowExecutionStarted` event. If
   history has none, it starts at the source workflow task's `created_at`.
2. It moves forward to the `created_at` of each command event the replay
   consumes, of each `TimerFired` event when a timer resolves, and of each update
   boundary it applies. It never moves backwards.
3. Wall time, live task state and unconsumed events never change it.

Go `Context.Now()`, Python `workflow.now()` and a new TypeScript
`workflowInfo().now` (a new `Date` per call) read this clock in UTC. Workflow,
query and update replay therefore observe the same value at the same point.

Scheduling a new timer is a side effect that runs once, so its `fireAt` stays
wall time plus the duration. Using the logical clock would schedule the timer in
the past.

Activity and child outcomes come from live task state, not fetched history. If
the clock advanced on their completion events, a completion recorded between
the history fetch and the task read would change the observed time on the next
replay. After an activity or child returns, the clock therefore still shows the
latest consumed history event. Precise completion time would need the runtime to
record task-resolution boundaries in history. That is an open gap for web
coordination, not part of this design. Workflows needing wall time call an
activity.

### Replay introspection

Python `workflow.unsafe.is_replaying()` returns `True` during query and update
replay until an update handler starts running live. During workflow replay it
returns `True` while unconsumed command events or update boundaries remain.
`is_replaying_history_events()` returns the same value. Outside a workflow
runtime both keep returning `False`, which is truthful. The exported names do
not change.

## Module ownership

Replay moves out of the Agent runtime modules:

- TypeScript: `typescript/src/agent/_replay.ts`.
- Python: `python/src/postgrip/agent/_replay.py`.

Each module owns history cursors, update boundaries, the logical clock and a
replay-owned `DeterminismError`. It imports only history types: no SDK failure
types, connection, workflow runtime or task dispatch. Query and update handler
registries are per-invocation runtime state and stay with the Agent. The Agent
translates `DeterminismError` into a non-retryable `ApplicationFailure` at its
dispatch boundary, as Go's `translateReplayError` does. Neither module is
exported from a package entry point.

## Compatibility

No public name is removed, and no contract, wire format or runtime-service
behavior changes. These changes are observable:

- TypeScript and Python workflows whose command order differs from history fail
  with a determinism error instead of reusing recorded results.
- The TypeScript and Python determinism failure type changes from
  `DeterminismViolation` to `WorkflowDeterminismViolation`, matching Go and the
  language guides.
- TypeScript and Python updates apply at their recorded positions. As in Go, a
  pending update before a command suspends the workflow task, and a handler
  registered after its update's position fails with a determinism error. Update
  handlers can issue commands in update tasks.
- Go `Now()` and Python `workflow.now()` return logical time, which on a first
  run is the workflow start time. TypeScript gains `workflowInfo().now`.
- Python `is_replaying()` reports replay state.

## Delivery slices

Each slice is its own PR under the [review process](../development/contributing.md)
and updates the affected language guides (`go/agent/docs`, `typescript/docs`
and `python/docs` `workflow-runtime.md`) in the same PR.

1. **Extraction.** Move TypeScript and Python replay into `_replay` modules with
   the replay-owned `DeterminismError`, translated at Agent dispatch. Keep
   behavior unchanged, including the `DeterminismViolation` type.
2. **Command order.** Add the ordered command cursor to TypeScript and Python,
   align the failure type, and add the shared ordering fixtures to all three
   languages.
3. **Updates.** Apply TypeScript and Python updates at their boundaries and run
   update tasks live after their own boundary, with shared fixtures for all
   three languages.
4. **Logical clock.** Add the replay clock to Go, Python and TypeScript.
5. **Introspection.** Report Python replay state.

## Acceptance

Shared conformance fixtures live in `test/fixtures/replay/` as JSON: a history,
a list of replay operations (activity, timer, child, update boundary, clock read)
and the expected result of each. Each language's replay unit tests run every
fixture. They cover:

- reordered activity/timer, timer/child and activity/child histories failing
  with a determinism error, and matching orders replaying;
- identity mismatches and retry attempts;
- `Activity(A), UpdateAccepted(set), UpdateCompleted(set)` not applying `set`
  before `Activity(A)` is consumed, plus pending, failed and legacy
  completion-only updates;
- clock values from start, command, `TimerFired` and update events, including
  the task `created_at` fallback, and that equal histories yield equal values.

Language runtime tests add:

- a workflow whose branch depends on the clock taking the same branch on
  redelivery;
- an update task that schedules an activity under its own task ID and blocks;
- a query replay that stops at a pending update;
- the determinism failure type and the Python introspection values.

Existing Agent tests, drift and generation checks, and strict documentation
builds pass apart from the changes listed under Compatibility.
