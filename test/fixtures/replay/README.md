# Replay conformance fixtures

Shared by the Go (`go/agent/internal/replay`), TypeScript
(`typescript/test/agent/replay.test.ts`) and Python
(`python/test/agent/test_replay_conformance.py`) replay tests, as specified in
[the workflow replay design](../../../docs/design/workflow-replay-conformance.md).

Each file holds a `history` of workflow history events, optional `owners` and
ordered `steps`. `owners` maps a command event's `task_id` to the task that
issued it, as the Agent reads it from the command task's payload; a command
owned by an update task in the history belongs to that update, and every other
command belongs to the workflow body.

A step issues one command (`activity` with `name`, `timer` with `duration_ms`,
or `child` with `workflow_type`) and expects `replay` (a recorded event is
consumed), `new` (no recorded command remains) or `nondeterministic` (a
determinism error, leaving the recorded event unconsumed). A step with `owner`
runs as that update task's handler: replayed by default, or live with
`"live": true`. A `complete` step runs the completion check's leftover test for
the body, and a `handler_done` step runs it for the step's `owner`; both expect
`ok` or `nondeterministic`.
