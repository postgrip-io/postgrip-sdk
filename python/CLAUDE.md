# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Unified Python SDK for PostGrip Agent, Worker-management, and
Service-management APIs. Agent runtime wire shapes come from `../go/protocol`
and are mirrored into `src/postgrip/agent/types.py`. Root CI compares the
definitions atomically.

The PyPI distribution and root module are `postgrip`; `postgrip.agent` is its
Agent submodule. The Agent API follows the Temporal Python SDK:
`Client.connect`, `Agent`, `@workflow.defn` / `@activity.defn`, and workflow
execution helpers.

## Commands

```sh
# Install in dev mode (with src/ layout means PYTHONPATH must include src for direct test runs)
pip install -e .

# Run all tests
PYTHONPATH=src python -m unittest discover -s test

# Run a single test file or test method
PYTHONPATH=src python -m unittest test.test_python_sdk
PYTHONPATH=src python -m unittest test.test_python_sdk.TestX.test_specific_thing

# Build wheel locally (matches CI's check)
python -m pip wheel --no-deps . -w /tmp/wheel
```

Root CI (`../.github/workflows/ci.yml`) runs the wheel build, tests on Python 3.11 / 3.12 / 3.13, and the cross-language drift guard. A drift failure means the same commit contains incompatible wire definitions.

## Architecture

### Module layout

```
src/postgrip/
├─ __init__.py        Lazy root facade and public root exports.
├─ client.py          PostGrip and AsyncPostGrip root facades.
├─ agent/             Agent runtime and management surface.
├─ worker/            Worker-management client and generated contract.
├─ service/           Service-management client and generated contract.
└─ _internal/         Shared configuration and transport mechanics.
```

Within `src/postgrip/agent/`:

```
├─ __init__.py        Re-exports the Agent public surface.
├─ client.py          Client, Connection, TaskClient, WorkflowClient, ScheduleClient, WorkflowHandle
├─ agent.py           Agent — the polling worker. (Equivalent of Go's worker.Worker.)
├─ worker.py          Backwards-compat alias to Agent (Worker = Agent). Legacy import name.
├─ workflow.py        Decorators (@defn, @run, @signal, @query, @update), workflow-side runtime,
│                     context-var stash, sandbox checks for nondeterministic APIs.
├─ activity.py        Activity decorators + contextvar-stashed runtime, milestone / heartbeat
├─ errors.py          ApplicationFailure, CancelledFailure, TimeoutFailure, TaskFailedError
└─ types.py           Wire-format dataclasses / TypedDicts mirroring agent-sdk-protocol/types.go
```

`__init__.py` is the customer-facing import surface. New public types must be added there explicitly; rely on `__all__` to keep the exposed surface deliberate.

### How the workflow runtime works

Same model as the Go SDK, just async-Python-flavored. Each workflow task lease:

1. Agent fetches the workflow's full durable history.
2. Agent constructs a workflow runtime (`_WorkflowRuntime` in `workflow.py`) wired to the history cursor.
3. Agent invokes the customer's `@workflow.run` coroutine.
4. Calls inside the coroutine (`workflow.execute_activity`, `workflow.sleep`, `workflow.execute_child`, signal/query/update channel reads) consult the cursor first.
   - History records this command, completed → return persisted result.
   - History records it, in-flight → `await` suspends until the runtime resolves the awaited future.
   - History exhausted → schedule a new command and suspend.
   - Mismatch with recorded command → raise a non-retryable `ApplicationFailure` tagged `WorkflowDeterminismViolation`.

When the coroutine returns (or raises), the agent reports the result back as a task completion. **Suspension is via Python `await` semantics, not via raising a sentinel** — that's the key difference from Go, where the body returns an error sentinel. Don't try to "fix" suspension by raising; it's load-bearing that the coroutine yields control back to the agent's event loop instead.

### `ContinueAsNewCommand` is raised, not returned

Unlike `Suspended`, `ContinueAsNew` *is* a sentinel exception (`workflow.ContinueAsNewCommand`). Customer workflow code calls `workflow.continue_as_new(...)` which raises this; the agent catches it and translates to a runtime-service ContinueAsNewResult on completion. Don't change this to a return value — `continue_as_new` from inside nested helpers / scopes works only because the exception propagates.

### Sandbox checks

`workflow.py` has an AST-walking sandbox that rejects common nondeterministic APIs (`time.time()`, `time.sleep()`, `asyncio.sleep()`, `random.*()`, `uuid.uuid4()`) at workflow definition load time. It runs once when `@workflow.defn` is applied and raises `ApplicationFailure` if it sees one of these. **Customer workflows must use `workflow.now()`, `workflow.sleep()`, explicit IDs, or activity calls instead.** The sandbox is a static check — it can't catch dynamically-imported nondeterministic code, so document the rule prominently in customer-facing material rather than relying on the sandbox as a hard guarantee.

### Activity context

`activity.py` uses `contextvars.ContextVar` to stash an `_ActivityRuntime` per in-flight activity invocation. Helpers (`activity.heartbeat`, `activity.milestone`, `activity.info`) read from the context var. Calling them outside an activity raises a `RuntimeError` rather than silently no-oping. The contextvar is set up by `agent.py` immediately before invoking the customer's activity coroutine.

### Custom decoder semantics

`types.py` carries dataclasses that round-trip with the Go wire structs. Some Go fields use `*time.Time` (RFC3339 string on the wire); the Python side must accept both RFC3339 and `null`/missing without crashing. Don't assume any timestamp is always present.

## Polyglot mirror

This is one of three language packages sharing the Agent runtime contract:

- `../go/protocol` — wire-shape source of truth (Go).
- `../go` — unified Go SDK; imports protocol directly.
- `../typescript` — TypeScript SDK; mirrors types in `src/agent/types.ts`.
- `python/` — this package; mirrors types in `src/postgrip/agent/types.py`.

Wire-shape changes must update protocol and each mirror in one commit. The drift guard catches name-level disagreement; it does **not** catch type-level drift (int vs str, optional vs required) — those need human review.

## Distribution

The PyPI package and Python root module are both `postgrip`. Releases are
gated on a `python/v*` tag which fires
`../.github/workflows/publish-python.yml`. Configure PyPI trusted publishing
for repository `postgrip-sdks`, workflow `publish-python.yml`, and environment
`pypi`.

To cut a release:

```sh
git tag -a python/v0.X.Y -m "Python v0.X.Y"
git push origin python/v0.X.Y
```

The version in `pyproject.toml` must match the tag suffix. The workflow creates
the GitHub release after PyPI publishing succeeds.

## Docs

The customer-facing docs site is built with MkDocs Material from `docs/` and
`mkdocs.yml`, then published under the monorepo's GitHub Pages site.
