# Replay conformance fixtures

Shared by the Go (`go/agent/internal/replay`), TypeScript
(`typescript/test/agent/replay.test.ts`) and Python
(`python/test/agent/test_replay_conformance.py`) replay tests, as specified in
[the workflow replay design](../../../docs/design/workflow-replay-conformance.md).

Each file holds a `history` of workflow history events and ordered `steps`.
A step issues one command (`activity` with `name`, `timer` with `duration_ms`,
or `child` with `workflow_type`) and expects `replay` (a recorded event is
consumed), `new` (no recorded command remains) or `nondeterministic` (a
determinism error, leaving the recorded event unconsumed).
