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
  workflow completes. Every language raises a recorded cancellation at the
  first command, wherever the request sits in history.
- **Update position.** TypeScript and Python run every completed update as soon
  as its handler is registered, before earlier commands are replayed, and ignore
  `WorkflowUpdateAccepted`. Their registration is synchronous, so an `async`
  handler is never awaited. Their update tasks replay the whole workflow in query
  mode and only then call the handler, so a handler cannot issue commands. Go
  applies each update at its accepted position (`NextUpdateBeforeCommand` and
  `ConsumeUpdate`). However, `runWorkflowUpdate` ignores whether
  `ConsumeUpdate(task.ID)` succeeded and runs the handler even when an earlier
  update is still pending. In every language, a body and an update handler that
  issue commands concurrently share one cursor, so either can consume the
  other's recorded command.
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

### Command ownership

Command events are `ActivityTaskScheduled`, `TimerStarted` and
`ChildWorkflowExecutionStarted`. History does not say which execution issued a
command, and a workflow body and an update handler can issue commands
concurrently. The command's own task records it, though. Each command event's
`task_id` names the task the command created, and that task's payload names the
task that scheduled it: `workflowTaskId` for activities and timers, and
`parentWorkflowTaskId` for child workflows. Body commands carry the workflow
task's ID, and update handler commands carry their update task's ID. The runtime
copies the payload into activity retry attempts, and task payloads never change.

Before running replay, the Agent reads the owner of every command event that
could belong to an update, once per replay:

- for an accepted entry, events between its accepted event and its terminal
  event, or the end of history while it is pending;
- for a legacy entry (see **Update boundaries**), events before its terminal
  event.

It passes the resulting owner map to the replay engine, which itself performs
no I/O. Every other command event belongs to the body. If a command's task
cannot be read, the Agent treats it like a failed history fetch.

### Ordered command cursors

The body and each update entry have their own cursor over the command events
they own. When the body issues a command of kind K:

1. If no unconsumed body-owned command event remains, the command is new: the
   runtime schedules it, or stops replay in query and update replay.
2. If the earliest unconsumed body-owned event is not of kind K, fail with a
   determinism error naming the recorded and requested kinds. This covers both
   reordering and a kind with no events left.
3. Otherwise compare recorded identity before consuming the event:
   `activity_type`, `workflow_type`, or `duration_ms` for timers. A mismatch is
   a determinism error and leaves the event unconsumed. A match consumes it.

TypeScript and Python workflows can issue commands concurrently (for example
`Promise.all` or `asyncio.gather`), and each new command is enqueued by its own
request, so the runtime could record them in a different order than the calls.
The runtime therefore schedules new commands one at a time, in call order, for
each workflow invocation, so history records them in the order replay consumes
them.

Replay state records every determinism error it raises. Once one is recorded,
the workflow task fails with that error when the workflow returns, raises,
continues as new or suspends, even if workflow code caught the error and went
on. Caught nondeterminism therefore cannot complete a workflow.

A replayed update handler follows the same rules over its own events. Its
completed or failed handler already finished, so when none of its events
remain, a further command is a determinism error, never a new command. Only an
update task's live handler (below) schedules new commands. An activity retry
consumes the retry attempt's event under the same rule. Query, update and
workflow replay use the same cursors.

**Cancellation.** A recorded `WorkflowCancellationRequested` is observed only
when no unconsumed command event owned by the executing context, and no
unapplied update boundary, precedes it in history. The executing context is the body, or the update handler that is
running. A replayed completed or failed handler never observes a request
recorded after its own terminal event, because its original execution finished
before that request existed. This applies at every cancellable point (before a command, and in
`condition`) and to the synchronous `cancellationRequested()` accessors of
TypeScript (`workflow.ts`) and Python (`workflow.py`). Commands recorded before
the request replay normally, including those of an update handler that issued
them before the request, and the first cancellable point or accessor read after
them observes the cancellation. Today every language raises it at the first
command, and the accessors report it from workflow entry, wherever the request
sits in history.

**Completion check.** Before a workflow task completes or continues as new, the
runtime applies any remaining update boundaries in strict mode (below). If
history records a cancellation request that the body has not yet observed, and
the body is in a cancellable scope, the runtime raises the cancellation failure
at this point instead of completing. A workflow that finishes its last command
after a request therefore still observes it, as every language does today. If a
body-owned command event is still unconsumed, the task fails with a determinism
error instead of completing. When a replayed handler returns or raises, any of
its own events left unconsumed are a determinism error too. The check does not
run when the workflow fails. Because cancellation is positional, a workflow that
handles cancellation and returns has consumed every command recorded before the
request, so no exemption is needed.

### Update boundaries

Build an ordered update list from `WorkflowUpdateAccepted` events. Matching
`WorkflowUpdateCompleted` and `WorkflowUpdateFailed` events, by `task_id`, mark
an entry completed or failed and record that terminal event's index. A
completion or failure event without an accepted event is a legacy entry from an
older runtime. It is positioned at its earliest owned command event, or at its
terminal event when it owns none, so its handler can replay through the commands
it issued.

**Handler-started marker.** A failed update whose handler never ran must not be
replayed. Examples are a `WorkflowUpdateConflict`, a missing handler, or an
invalid payload. Neither ownership nor history tells that case apart from a
handler that ran, changed state and raised without issuing a command. Before an
update task runs its handler live, it appends a task event to its own task with
stage `update-handler-started`. Appending a task event is not idempotent, so
an append can persist and still report failure. When the append fails, the task
reads its own events: if the marker is present it runs the handler, and
otherwise it fails without running the handler. If that read also fails, the
task neither completes, fails nor blocks. It stops renewing its lease and
leaves the task leased, so the runtime redelivers it on lease expiry, as it
does after a crash. The redelivered task repeats the reconciliation. Blocking
would strand it, because nothing wakes a blocked update task that has issued
no command. While building replay state, the Agent reads each completed or
failed update task's events once, and passes the set of marked task IDs to the
replay engine. A terminal task's events do not change, so every replay sees the
same set.

The marker also versions completed updates. An unmarked completed entry was
recorded by an SDK release before this design, and replays with that
language's previous registration behavior so existing workflows are not
stranded. A Python unmarked entry closes an `async` handler's coroutine without
running it, because the previous release never ran it. A TypeScript unmarked
entry invokes the handler without awaiting it, as before. Go is unaffected. The
awaited in-flight rules below apply to marked entries only.

The next update boundary applies only when its index precedes the earliest
unconsumed body-owned command event, or when none remain. Applying a boundary
consumes it:

- **Strict** application runs before each durable command and in the completion
  check. A completed entry runs its registered handler with the recorded `args`,
  and the runtime awaits it to completion. A missing handler is a determinism
  error. A failed entry runs its handler the same way, and expects it to raise,
  when it has the marker or owns at least one command event. Owned commands
  prove the handler ran, which covers legacy failures and failures recorded
  before markers existed. Control-flow and infrastructure errors raised inside
  either kind of handler propagate unchanged. These are replay determinism
  errors, suspension, cancellation, and the SDK's own transport and adapter
  errors, such as a failed read of an owned command's task. They fail or
  redeliver the workflow task without consuming the boundary. Any other error is
  an application outcome. For a failed entry it is the recorded failure, which
  does not fail the workflow, and a handler that returns instead is a
  determinism error. For a completed entry it contradicts the recorded success,
  so it becomes a recorded (sticky) determinism error even if workflow code
  catches it. A failed entry with neither the
  marker nor owned commands is consumed without running a handler, as today. A pending entry suspends the workflow task until the update finishes.
- **Deferred** application runs after each durable command and on handler
  registration. It applies
  boundaries the same way, but stops without error at a missing handler or a
  pending entry, so later code can register the handler.

Entries apply in the order of their positions. Before the conflict rule
(below), runtimes could record overlapping updates, for example
`Accepted(U1), Accepted(U2), Completed(U2), Completed(U1)`. Each of those
handlers originally ran without the other's effect, so no replay order
reproduces both. Replay keeps acceptance order, which is deterministic and is
what Go uses today. Failing such histories would strand running workflows. The
conflict rule prevents new overlaps.

Registering a handler also applies deferred boundaries in every language, as
Go does today. The workflow code that follows registration therefore observes
the update, which is also how TypeScript and Python histories were recorded
before this design. TypeScript and Python registration is synchronous while
their handlers may be `async`. Registration invokes each replayed handler
synchronously, so a synchronous handler's effects are fully visible when
registration returns. An `async` handler is tracked as in flight:

- A TypeScript `async` handler runs up to its first `await` during
  registration.
- Calling a Python `async def` handler only creates its coroutine, so none of
  its body runs during registration.

Before the body's next command is consumed, before the body re-evaluates a
`condition` predicate, and before completion, the runtime awaits every
in-flight replayed handler in boundary order. Later boundaries apply only after
it settles. A handler's own operations, its commands and `condition` waits, do
not wait at that barrier. They run in the handler's execution context and
consume the handler's owned events, so a handler never awaits itself or a later
handler.

Each execution context (the body and each running handler) has its own
cancellation-scope stack. Today TypeScript keeps one mutable
`cancellationScopes` array per invocation, and Python one scope `ContextVar`
that concurrent tasks may share. A handler that enters
`CancellationScope.nonCancellable()` and suspends must not change the scope the
body sees. TypeScript keys the stack by execution context, for example through
`AsyncLocalStorage`. Python gives each handler task its own context copy with
an independent stack. TypeScript and Python runtimes also apply deferred boundaries before
evaluating a `condition` predicate.

Workflow code that runs between registration and its next durable call,
including the arguments of that call, therefore sees an `async` handler's
effects only up to the point the language ran synchronously. Code after that
call sees all of them. This is deterministic: the run that first recorded the
command after the boundary applied the same synchronous prefix at the same
point, so every replay chooses the same command. A workflow whose next command
depends on an `async` handler's later effects awaits a `condition` on that
state before issuing it.

Signals keep their delivery rule: every recorded signal is delivered when its
handler is registered. Signal handlers must be synchronous, and a signal handler
must not issue workflow commands or wait on a `condition`. Today TypeScript
discards an `async` signal handler's promise, so its workflow calls would race
the body for body-owned events. Python discards an `async def` signal handler's
coroutine, so it never runs. Ordering them would need positional signal delivery
(see the gap below), and running Python's would change existing histories.
TypeScript therefore rejects a workflow command or `condition` issued from a
signal handler's execution context with a non-retryable
`SignalHandlerCommandUnsupported` failure. Python logs a warning when an
`async def` signal handler is registered and keeps not running it. The
TypeScript and Python guides state the rule.

**Body and update overlap.** The runtime unblocks the workflow task when an
update is accepted, so a body run that fetched history before the acceptance
can record a command after `Accepted(U)` that was chosen without U's effect.
History records no workflow-task boundary, so replay cannot tell that command
from one chosen after U applied, and replay applies U at its accepted position.
A body whose command choice depends on U's state can then fail with a
determinism error on replay. The SDK cannot order this race alone. The runtime
must either serialize update tasks with their source workflow task, or record
workflow-task boundaries in history. That is an open gap for web coordination,
shared with Go today.

Cancellation has the same race. A run that fetched history before a
cancellation request can schedule a command recorded after
`WorkflowCancellationRequested`. Positional replay then observes the
cancellation before that command, so code that handles cancellation finds the
command left over. Signals have the same race: a run that fetched history
before `WorkflowSignaled(S)` can record a command after S that was chosen
without S, while replay delivers S at handler registration. The same runtime
remedies apply to both, and both are recorded in the same open gap. Signal
delivery stays deterministic for runs that do not race.

**Update tasks.** An update task replays its source workflow in replay-only
mode until replay stops. It then inspects the next unconsumed update boundary:

- If it is this task's own boundary, the task consumes it and runs the handler
  live with the update task's ID. The handler's cursor first replays the
  commands it already owns from an earlier delivery of this task. Its new
  commands are scheduled with that ID as `workflowTaskId`, so their completion
  wakes the update task, and a suspension blocks the update task.
- If an earlier update is still pending ahead of it, the task fails with a
  non-retryable `WorkflowUpdateConflict` failure and never runs the handler.
  Blocking is not safe here. The runtime wakes a blocked task only through the
  `workflowTaskId` of a command it issued, so nothing would wake an update task
  blocked behind another update. Queueing such updates needs that runtime wake
  path, which is an open gap for web coordination.
- Any other position is a determinism error.

Query tasks replay the same way and stop at the first new command or pending
boundary. A query replay that instead returns normally runs the completion
check's leftover-command test, and a recorded determinism error fails the query
task. A query is served only from state consistent with durable history.

### Logical clock

Replay state owns the workflow clock:

1. It starts at `created_at` of the first `WorkflowExecutionStarted` event. If
   history has none, it starts at the source workflow task's `created_at`.
2. It moves forward to the `created_at` of each command event the replay
   consumes, of each `TimerFired` event when a timer resolves, of each update
   boundary it applies, and of the cancellation request when it is first
   observed. It never moves backwards.
3. Before it moves to an event's time, the replay applies, in deferred mode,
   every update boundary with a lower history index. A timer that resolves as
   fired therefore applies the boundaries recorded between `TimerStarted` and
   `TimerFired` before the clock reaches the fire time. Those handlers observe
   the same time whether or not the timer had fired when the replay ran.
4. Wall time, live task state and unconsumed events never change it.
5. Every value is truncated to whole milliseconds, the precision of a
   TypeScript `Date`. Go and Python therefore expose the same instant as
   TypeScript for the same history.

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

- It is `True` during query and update replay. A redelivered update task's
  live handler keeps reporting `True` while it replays the commands it already
  owns, and switches to `False` when its cursor is exhausted and it reaches
  live execution.
- While a completed or failed update's handler is replayed, it is `True`. Its
  terminal event proves the handler already ran, even for a legacy entry
  positioned at that terminal event.
- During workflow replay, the current position is the history index of the
  latest consumed command event or applied update boundary. While a recorded
  signal is delivered to its handler, the position is that signal's index. The
  helper returns `True` when history has a workflow-produced event at a higher
  index than the current position. Workflow-produced events are command events
  and update accepted, completed and failed events.

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
- The body and each update handler replay only the commands they issued. To
  learn ownership, the Agent reads the task of each command recorded while an
  update was open, once per replay.
- A recorded cancellation is observed after the commands recorded before it
  have replayed, instead of at the first command. The cancellation failure the
  workflow first observes is unchanged.
- The TypeScript and Python replay determinism failure type, and the TypeScript
  sandbox failure type, change from `DeterminismViolation` to
  `WorkflowDeterminismViolation`, matching Go and the language guides.
- TypeScript and Python updates apply at their recorded positions instead of
  all at once, still starting at registration, and their `async` handlers are
  awaited before the next command, condition or completion.
  As in Go, a pending update before a command suspends the workflow task, and an
  update whose handler is missing at a strict point fails with a determinism
  error. Update handlers can issue commands in update tasks.
- In every language, an update task that finds an earlier update still pending
  fails with `WorkflowUpdateConflict`. Update tasks append an
  `update-handler-started` task event before running their handler, and a
  failed update whose handler ran replays that handler.
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
2. **Command order**, in three PRs, each in all three languages with shared
   fixtures:
   1. **Ordered cursor.** One ordered cursor per invocation, with the identity
      check before consumption, sticky determinism errors on every exit from
      workflow and interaction replay, new commands scheduled in call order
      that stop after an earlier enqueue fails, and the aligned TypeScript and
      Python failure types. Until slice 2.2, commands issued by update handlers
      share the invocation's cursor, as they shared the per-kind cursors before.
   2. **Ownership and completion.** Command ownership, the per-owner ordered
      cursors and the completion check.
   3. **Positional cancellation.**
3. **Updates.** Apply TypeScript and Python updates at their boundaries from the
   runtime and run update tasks live after their own boundary. In all three
   languages, fail conflicting update tasks, add the handler-started marker,
   replay marked failed handlers and bound replayed handlers to their recorded
   segment, with shared fixtures.
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
  was removed, failing the completion check;
- `Activity(A), CancellationRequested` replaying A before raising the
  cancellation failure, with the accessor reporting `False` at workflow entry
  and `True` after A, and a changed workflow that returns without consuming A
  failing the completion check;
- `Accepted(U), Activity(A) owned by U, CancellationRequested, Failed(U)`,
  where U's replayed handler consumes A before observing the cancellation;
- `Accepted(U), Completed(U), CancellationRequested`, where the accessor reports
  `False` until U has applied, and U's replayed handler itself reads `False`;
- an `async` replayed handler that awaits its own owned command and a
  `condition` without deadlocking, and a body command after it that waits for
  it;
- an `async` handler inside `nonCancellable()` that suspends while the body's
  next cancellation check still uses the body's own scope;
- `Activity(A)`, then a workflow that returns after A against
  `Activity(A), CancellationRequested`, which raises the cancellation failure at
  completion, while a workflow that observed and handled it completes;
- `Activity(A at t0), CancellationRequested(at t1)`, where the clock reads `t1`
  once the cancellation is observed;
- workflow code that catches a determinism error and returns, which still fails
  the task with that error;
- a completed update whose replayed handler now raises, which fails the task
  with a determinism error even when workflow code catches the exception, and a
  marked failed handler whose owned command's task read fails, which propagates
  the transport error and leaves the boundary unconsumed;
- `Accepted(U), Activity(B) owned by the body, Completed(U)`, where U's handler
  now issues `Activity(B)`, failing with a determinism error while the body's B
  replays normally;
- a legacy completion-only update whose owned command precedes its completion,
  replayed through that command;
- identity mismatches and retry attempts;
- `Activity(A), UpdateAccepted(set), UpdateCompleted(set)` not applying `set`
  before `Activity(A)` is consumed, plus pending, failed and legacy
  completion-only updates;
- an update task's own boundary reached, an earlier pending update ahead of it,
  and a boundary that cannot be reached;
- a legacy or pre-marker failed update that owns a command, replayed through
  it; an overlapping `Accepted(U1), Accepted(U2), Completed(U2), Completed(U1)`
  history replaying in acceptance order;
- a failed update whose marked handler scheduled a command before raising,
  replayed so the command is consumed by the handler, not the body; an unmarked
  failure consumed without running its handler; a marked failed handler that
  returns instead of raising failing with a determinism error; and a marked
  failed handler whose replayed command mismatches, which propagates the
  determinism error instead of counting it as the recorded failure;
- a completed update whose handler now issues a command its recorded segment
  lacks, failing with a determinism error instead of scheduling it;
- clock values from start, command, `TimerFired` and update events, including
  the task `created_at` fallback, that equal histories yield equal values, and
  that signal and activity-completion events leave the clock unchanged, and
  that a `created_at` with sub-millisecond digits yields the same millisecond
  value in every language;
- `TimerStarted`, a completed update, then `TimerFired`, where the update
  handler observes the same clock value before and after the fire is recorded.

Language runtime tests add:

- a workflow whose branch depends on the clock taking the same branch on
  redelivery;
- in TypeScript and Python, a synchronous update handler whose state the code
  right after registration observes, as in
  `setHandler(U); await activity(flag ? 'A' : 'B')`; an `async` handler that
  awaits a command and then changes state, where code after the workflow's next
  durable call observes the change, and that call's arguments see the same
  state on every replay; and a body that waits on a `condition` for the async
  state before choosing its command;
- an update task that appends its `update-handler-started` event, schedules an
  activity under its own task ID and blocks; a second update task that fails
  with `WorkflowUpdateConflict` without appending the event or running its
  handler; an update task whose marker append fails but persisted, which runs
  its handler after reading its events; one whose append failed without
  persisting, which fails without running its handler; and one whose
  reconciliation read also fails, which stops renewing its lease and is
  redelivered;
- a query replay that stops at a pending update, and a query whose changed
  workflow returns before a recorded trailing command, which fails instead of
  serving the query;
- an unmarked completed update with a Python `async def` handler that replays
  without running the coroutine, and a marked one that runs it;
- a TypeScript signal handler that issues an activity, which fails with
  `SignalHandlerCommandUnsupported`, and a Python `async def` signal handler
  registration that logs a warning;
- the determinism failure type for replay and the TypeScript sandbox;
- Python introspection values for commands, updates, a signal followed by a
  command, a signal-only history, a completed update at the end of history, a
  legacy completion-only update, and a redelivered update task before and after
  its recorded prefix.

Existing Agent tests, drift and generation checks, and strict documentation
builds pass apart from the changes listed under Compatibility.
