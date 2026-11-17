# Cancellation cleanup replay in TypeScript and Python

Implements SDK issue #152. Status: implemented; local and managed-stage validation recorded in
[test evidence](https://github.com/postgrip-io/postgrip-sdk/blob/f743e01bb9923d5d1e216c79ff31f80a97b4fae3/test/live/cancellation-cleanup-20261117.md).

## Problem and scope

The workflow facade and Agent check a history-wide cancellation flag before
consuming commands. On replay of `TimerStarted, WorkflowCancellationRequested`,
sleep raises immediately. A non-cancellable cleanup activity then encounters
the unconsumed timer and fails determinism validation. This is an SDK defect;
the existing server history and scoped cancellation APIs are sufficient.

This slice implements cancellation at the executing owner's ordered command
boundary in TypeScript and Python. It does not implement the broader proposed
update scheduling/logical-time work in [replay conformance](workflow-replay-conformance.md),
change Go behavior, HTTP contracts, cancellation propagation policy or releases.

## Decisions

- The pure replay model determines cancellation visibility from the first
  cancellation event and the executing owner's next command position. A
  recorded command before that event must first be matched and consumed.
  Identity/kind mismatches still produce sticky determinism failures.
- The Agent checks cancellation both before consuming a command and immediately
  afterward, before returning a result or suspending. Thus the last command
  preceding cancellation is consumed and then interrupted. This applies even
  if its result/timer completion is now available: cancellation takes precedence
  at that boundary. Earlier recorded commands replay normally.
- An already-completed update owner does not see cancellation recorded after
  its terminal event. Owner cursors remain independent.
- The facade delegates command cancellation to the runtime, which owns replay
  position and read-only query behavior. The scoped cancellation accessor uses
  the same positional visibility, so finally cleanup is not entered on an
  ordinary suspension before that boundary.
- After draining commands, cancellation also takes precedence over a
  cancellable suspension returned by Promise.all/asyncio.gather: an earlier
  sibling can suspend before another consumes the final pre-cancellation
  command. Suspension exceptions carry their originating scope. A suspension
  from non-cancellable cleanup must remain blocked, so this resolution cannot
  terminate the workflow before cleanup completes. Sticky determinism errors
  retain highest precedence. This uses recorded position and scope, not a
  timing delay or scheduling heuristic.
- Non-cancellable scope suppresses the cancellation checks, not command
  matching. Its newly scheduled cleanup can suspend, then replay on a fresh
  Agent with the original timer consumed at the same boundary. After cleanup
  completes, the original cancellation exception propagates. Cancellation
  before the original timer was scheduled must not consume a cleanup command
  as though it were that timer.
- Queries remain read-only and stop at the same cancellation boundary without
  enqueueing commands. This slice does not promise queries execute cleanup.

## Ownership and compatibility

`_replay` owns pure history/position decisions; Agent orchestration owns
CancelledFailure/WorkflowQueryReady translation and command execution; the
workflow facade forwards scopes. No generated files, public exports or wire
types change. Existing histories need no migration. Workflows that previously
failed due to a changed command still fail; a terminal failed workflow is not
automatically reopened. Existing catch/finally semantics remain application
code: cleanup activities must be idempotent under at-least-once delivery.

## Validation

Both language regressions exercise real Agent dispatch with a recorded timer,
cancel, cleanup scheduling, a fresh Agent replay while cleanup is pending, and
cleanup completion followed by cancellation. Cover cancellation before timer
creation, a late TimerFired, completed commands preceding the timer, ordinary
suspension/completion without cleanup, command divergence, independent owners,
and read-only query behavior. Run the affected suites first, then full language
and repository contract/layout/docs checks. Repeat both workflows through a
disposable managed runtime and record exact revisions, histories, terminal
outcomes and cleanup. Local transport fixtures are not live evidence.
