# Deterministic workflow replay across languages

Date: 2026-10-13. Status: proposed.

## Problem and boundaries

The SDK architecture audit of `main` at `3675b2f2` found that the three Agent
runtimes do not replay durable history the same way. Go's
`go/agent/internal/replay` is closest to the intended behavior, but it has gaps
of its own. The TypeScript and Python runtimes diverge further, and every
language reads wall time somewhere it promises logical time:

- **Logical time.** Go `workflow.Context.Now()` promises time that is durable
  across replays, but `newWorkflowContext` reads `time.Now()`. Python
  `workflow.now()` reads `datetime.now(timezone.utc)`. The TypeScript guide tells
  users to call `workflowInfo().now`, which does not exist. The same history can
  take a different time-dependent branch after redelivery.
- **Command order.** TypeScript and Python keep one cursor per command kind and
  never compare positions across kinds. A workflow that now runs `Timer(1000)`
  before `Activity(A)` against history `Activity(A), Timer(1000)` reuses both
  results instead of failing. Go rejects that order in `checkCommandOrder`.
  However, no language rejects a command whose kind is exhausted while a command
  of another kind remains, so `Timer` against history `Activity(A)` is
  scheduled as new. No language checks for recorded commands left over when the
  workflow completes.
- **Update position.** TypeScript and Python run every completed update as soon
  as its handler is registered, before earlier commands are replayed, and ignore
  `WorkflowUpdateAccepted`. Their registration is synchronous, so an `async`
  handler is not awaited. Their update tasks replay the whole workflow in query
  mode and only then call the handler, so a handler cannot issue commands. Go
  applies each update at its accepted position (`NextUpdateBeforeCommand` and
  `ConsumeUpdate`). However, `runWorkflowUpdate` ignores whether
  `ConsumeUpdate(task.ID)` succeeded and runs the handler even when an earlier
  update is still pending.
- **Replay introspection.** Python `workflow.unsafe.is_replaying()` and
  `is_replaying_history_events()` always return `False`.
- **Ownership.** `WorkflowReplay` lives in `typescript/src/agent/agent.ts` and
  `python/src/postgrip/agent/agent.py` beside polling and dispatch, and builds
  `ApplicationFailure` itself. Its failure type, and that of TypeScript's
  `validateWorkflowSandbox`, is `DeterminismViolation`. Go and all three
  language guides use `WorkflowDeterminismViolation`.

This design changes only how the Agent runtimes replay history they already
fetch. Contracts, wire types, the runtime service, history event shapes, signal
delivery, activity and child resolution through live task state, and Agent
transport do not change. Follow [architecture](../development/architecture.md),
[contracts](../development/contracts.md) and [validation](../development/testing.md).

## Replay semantics

Every language implements the following over the history returned by
`getWorkflowHistory`, in history order. Where Go differs, Go changes too.

### Ordered command cursor

Command events are `ActivityTaskScheduled`, `TimerStarted` and
`ChildWorkflowExecutionStarted`. When workflow code issues a command of kind K:

1. If no unconsumed command event of any kind remains, the command is new: the
   runtime schedules it, or stops replay in query and update replay.
2. If the earliest unconsumed command event is not of kind K, fail with a
   determinism error naming the recorded and requested kinds. This covers both
   reordering and a kind with no events left.
3. Otherwise consume it and compare recorded identity: `activity_type`,
   `workflow_type`, or `duration_ms` for timers. A mismatch is a determinism
   error.

An activity retry consumes the retry attempt's `ActivityTaskScheduled` event
under the same rule. Query, update and workflow replay use the same cursor.

**Completion check.** Before a workflow task completes or continues as new, the
runtime applies any remaining update boundaries in strict mode (below). If a
command event is still unconsumed, the task fails with a determinism error
instead of completing. The check does not run when the workflow fails, or when
history records a cancellation request. Cancellation surfaces at the next
command, wherever that command sits in history, so it can leave recorded
commands unconsumed.

### Update boundaries

Build an ordered update list from `WorkflowUpdateAccepted` events. Matching
`WorkflowUpdateCompleted` and `WorkflowUpdateFailed` events, by `task_id`, mark
an entry completed or failed. A completion or failure event without an accepted
event is a legacy entry positioned at its own index.

The next update boundary applies only when its index precedes the earliest
unconsumed command event, or when no command events remain. Applying a boundary
consumes it:

- **Strict** application runs before each durable command and in the completion
  check. A failed entry is consumed without running a handler. A completed entry
  runs its registered handler with the recorded `args`, and the runtime awaits it
  to completion. A missing handler is a determinism error. A pending entry
  suspends the workflow task until the update finishes.
- **Deferred** application runs after each durable command. It applies
  boundaries the same way, but stops without error at a missing handler or a
  pending entry, so later code can register the handler.

Go also applies deferred boundaries inside `SetUpdateHandler`, because Go
handlers are synchronous. TypeScript and Python registration is synchronous
while their handlers may be `async`, so registering a handler there applies
nothing. Their runtimes also apply deferred boundaries before evaluating a
`condition` predicate. Every application point therefore runs inside the
runtime, which awaits each handler before the workflow issues its next command,
re-checks a condition, or completes. Workflow code that reads state between
registering a handler and its next durable call sees the state from before the
update.

Commands issued by a replayed update handler consume the history that follows
its boundary. Signals keep their current behavior: every recorded signal is
delivered when its handler is registered.

**Update tasks.** An update task replays its source workflow in replay-only
mode until replay stops. It then inspects the next unconsumed update boundary:

- If it is this task's own boundary, the task consumes it and runs the handler
  live with the update task's ID. Commands the handler issues are scheduled with
  that ID as `workflowTaskId`, so their completion wakes the update task, and a
  suspension blocks the update task.
- If an earlier update is still pending ahead of it, the task fails with a
  non-retryable `WorkflowUpdateConflict` failure and never runs the handler.
  Blocking is not safe here. The runtime wakes a blocked task only through the
  `workflowTaskId` of a command it issued, so nothing would wake an update task
  blocked behind another update. Queueing such updates needs that runtime wake
  path, which is an open gap for web coordination.
- Any other position is a determinism error.

Query tasks replay the same way and stop at the first new command or pending
boundary.

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

The clock deliberately ignores two kinds of timestamped events, because either
would make the time at a code point depend on history recorded after it:

- Activity and child outcomes come from live task state, not fetched history.
  A completion recorded between the history fetch and the task read would
  change the observed time on the next replay.
- Every recorded signal is delivered when its handler is registered, whatever
  its position, so a later signal would move the clock at an earlier point.

After an activity, child or signal, the clock therefore still shows the latest
consumed history event. Precise time for these would need positional signal
delivery and runtime-recorded task-resolution boundaries in history. That is an
open gap for web coordination, not part of this design. Workflows that need
wall time call an activity.

### Replay introspection

Python `workflow.unsafe.is_replaying()` reports whether a previous run has
provably executed past the current point, because history records a later
workflow-produced event:

- It is `True` during query and update replay, until an update handler starts
  running live.
- During workflow replay, the current position is the history index of the
  latest consumed command event or applied update boundary. While a recorded
  signal is delivered to its handler, the position is that signal's index. The
  helper returns `True` when a command event or update boundary in history has a
  higher index than the current position.

A signal that is the latest event in history may be seen for the first time, so
its delivery reports `False`. `is_replaying_history_events()` returns the same
value. Outside a workflow runtime both keep returning `False`, which is
truthful. The exported names do not change.

## Module ownership

Replay moves out of the Agent runtime modules:

- TypeScript: `typescript/src/agent/_replay.ts`.
- Python: `python/src/postgrip/agent/_replay.py`.

Each module owns history cursors, update boundaries, the completion check, the
logical clock and a replay-owned `DeterminismError`. It imports only history
types: no SDK failure types, connection, workflow runtime or task dispatch.
Query and update handler registries are per-invocation runtime state and stay
with the Agent. The Agent translates `DeterminismError` into a non-retryable
`ApplicationFailure` at its dispatch boundary, as Go's `translateReplayError`
does. Neither module is exported from a package entry point.

## Compatibility

No public name is removed, and no contract, wire format or runtime-service
behavior changes. These changes are observable:

- Workflows whose command order or kinds differ from history, or that complete
  with recorded commands left over, fail with a determinism error instead of
  reusing recorded results or scheduling duplicates. This applies to all three
  languages.
- The TypeScript and Python replay determinism failure type, and the TypeScript
  sandbox failure type, change from `DeterminismViolation` to
  `WorkflowDeterminismViolation`, matching Go and the language guides.
- TypeScript and Python updates apply at their recorded positions, from the
  runtime rather than at registration, and their `async` handlers are awaited.
  As in Go, a pending update before a command suspends the workflow task, and an
  update whose handler is missing at a strict point fails with a determinism
  error. Update handlers can issue commands in update tasks.
- In every language, an update task that finds an earlier update still pending
  fails with `WorkflowUpdateConflict`.
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
2. **Command order.** Add the global ordered cursor and the completion check in
   all three languages, align the TypeScript and Python failure types, and add
   the shared ordering fixtures.
3. **Updates.** Apply TypeScript and Python updates at their boundaries from the
   runtime, run update tasks live after their own boundary, and fail conflicting
   update tasks in all three languages, with shared fixtures.
4. **Logical clock.** Add the replay clock to Go, Python and TypeScript.
5. **Introspection.** Report Python replay state.

## Acceptance

Shared conformance fixtures live in `test/fixtures/replay/` as JSON: a history,
a list of replay operations (activity, timer, child, update boundary,
completion, clock read) and the expected result of each. Each language's replay
unit tests run every fixture. They cover:

- reordered activity/timer, timer/child and activity/child histories, and a
  command whose kind is exhausted while another kind remains, failing with a
  determinism error, while matching orders replay;
- a deleted trailing command, and a trailing completed update whose handler
  was removed, failing the completion check, and a recorded cancellation
  exempting it;
- identity mismatches and retry attempts;
- `Activity(A), UpdateAccepted(set), UpdateCompleted(set)` not applying `set`
  before `Activity(A)` is consumed, plus pending, failed and legacy
  completion-only updates;
- an update task's own boundary reached, an earlier pending update ahead of it,
  and a boundary that cannot be reached;
- clock values from start, command, `TimerFired` and update events, including
  the task `created_at` fallback, that equal histories yield equal values, and
  that signal and activity-completion events leave the clock unchanged.

Language runtime tests add:

- a workflow whose branch depends on the clock taking the same branch on
  redelivery;
- in TypeScript and Python, an `async` update handler that awaits a command and
  then changes state, replayed so the workflow's next command observes the
  changed state;
- an update task that schedules an activity under its own task ID and blocks,
  and a second update task that fails with `WorkflowUpdateConflict` without
  running its handler;
- a query replay that stops at a pending update;
- the determinism failure type for replay and the TypeScript sandbox;
- Python introspection values for commands, updates, a signal followed by a
  command, and a signal-only history.

Existing Agent tests, drift and generation checks, and strict documentation
builds pass apart from the changes listed under Compatibility.
