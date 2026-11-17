# SDK #152 cancellation cleanup validation — 2026-11-17 UTC

Design: [cancellation cleanup replay](../../docs/design/cancellation-cleanup-replay-20261117.md).
Base SDK revision: `c0f3bd7301e81c5169acdf14f18ed788935a0a2b` plus this PR.
Native Agent built from web `36bd1f738a993cd74930ef4d304d37611a6cc6b6`.
Staging retained its existing control-plane release; this check changed no
server contract or deployed image.

## Reproduction and regression

The original real-runtime failure is recorded in
[SDK #152](https://github.com/postgrip-io/postgrip-sdk/issues/152):
`history=TimerStarted replay=ActivityTaskScheduled`. New Agent-dispatch tests
reproduced it before the implementation change and pass afterward in both
languages. The tests exercise the public workflow facade and real dispatch,
using recorded transport fixtures; they do not stand in for the live run below.

Coverage includes cancellation before any timer, after TimerStarted, with
TimerFired before/after cancellation, and after an earlier completed activity.
It also covers pending activities/children, cleanup scheduling and suspension,
a fresh Agent replay before/after cleanup completion, ordinary suspension and
completion without cleanup, genuine command divergence, query read-only
behavior, and cancellation visibility isolated to the executing command owner.

## Managed staging acceptance

Under lease `sdk-152-20261117`, a disposable native Agent hosted separate
TypeScript and Python workflow.runtime tasks. Only those runtimes received
host-injected delegated credentials. The management caller submitted outer
runtime tasks; workflow creation and cancellation used the delegated SDK client
inside each runtime. The scripts wait for TimerStarted and the blocked task,
then cancel, inspect history and assert the cleanup activity's result and the
workflow task's terminal cancellation failure.

| Language | Managed runtime task | Workflow run | Cleanup activity |
| --- | --- | --- | --- |
| TypeScript | `7f9cf8dd7bc78f6960056610f9dd9170` | `b9ff7fb880bc2fa4c6427b58dbfb58f4` | `844193980fbada064f455f890eeda5c9` |
| Python | `5be95ed05aba387392b90de38b236dd4` | `d2c9858618b1b2bd3f2306456530852f` | `f35d73eeb7b0eb50879a3ea0ea293739` |

Both outer runtimes succeeded (exit 0). Each workflow recorded exactly one
cleanup ActivityTaskScheduled, then ActivityTaskStarted/Completed, then
WorkflowExecutionFailed carrying `CancelledFailure` and the supplied reason.
The cleanup result was `audit:<unique workflow ID>`, also emitted by the activity.
No determinism violation or premature workflow success occurred. This proves
managed replay through cleanup suspension; process restart is covered by the
local fresh-Agent regressions, not claimed as an injected live process crash.

## Repeat

Provision the disposable native Agent under the stage lease using web's
`.github/actions/disposable-agent`. Use the same checkout path visible to that
host. Keep owner, management and delegated credentials in private files, never
in source or process arguments.

```sh
(cd typescript && bun install --frozen-lockfile && bun run build)
# Load the stage management environment privately. Set POSTGRIP_AGENT_URL to
# https://agentorchestrator.postgrip.app and POSTGRIP_URL to the stage front door.
# Set POSTGRIP_TEST_HOST_QUEUE to the disposable host's authorized queue.
# Set POSTGRIP_TEST_BUN and POSTGRIP_TEST_PYTHON to host executable paths.
bun test/live/cancellation-cleanup.mjs
```

The driver invokes the two checked-in runtime fixtures, asserts their exit
status and prints task results/events. It cancels outstanding outer tasks in
finally. Each runtime terminates its own workflow only if still nonterminal.
Always run the disposable-Agent `down` action and release the lease afterward;
baseline restoration removes fixture database state and outstanding timers.

## Local validation commands

```sh
(cd typescript && bun run typecheck && bun run build && bun run test)
PYTHONPATH=python/src python3 -m unittest discover -s python/test
python3 scripts/check_package_layout.py --self-test
python3 scripts/check_package_layout.py
python3 go/protocol/tools/check_drift.py --self-test
python3 go/protocol/tools/check_drift.py --monorepo
python3 scripts/generate_openapi.py --plane all --check
python3 scripts/generate_api_docs.py --check
python3 scripts/check_api_docs.py
mkdocs build --strict --site-dir /tmp/sdk152-docs
(cd typescript && mkdocs build --strict --site-dir /tmp/sdk152-docs-ts)
(cd python && mkdocs build --strict --site-dir /tmp/sdk152-docs-py)
```

This is an SDK source fix, not a registry release. The production web guide's
older pinned SDK and workaround remain valid until coordinated source-pin and
documentation updates. Previously failed workflows are not reopened by this fix.

## Validated review finding: concurrent timers

Codex review on PR #153 identified that Promise.all/asyncio.gather could surface
an earlier timer's WorkflowBlocked even though its sibling had observed
cancellation. Both Agent-dispatch regressions reproduced this: after the cleanup
activity completed, the workflow remained blocked instead of failing cancelled.

The follow-up preserves each suspension's cancellation scope and resolves a
cancellable suspension against cancellation after draining commands. Pending
non-cancellable cleanup remains blocked; once cleanup completes, cancellation
wins over the earlier cancellable suspension. Sticky determinism checks remain
first. Full suites passed: TypeScript 786 tests, Python 263 with the one existing
environment-gated server smoke skip.

Under a second lease `sdk-152-20261117-r2`, the managed fixtures repeated both
single-timer and concurrent-timer scenarios in both languages:

| Language | Concurrent timers | Runtime task | Workflow run | Cleanup activity |
| --- | --- | --- | --- | --- |
| typescript | no | `636b78e951a658bd1a210a38aa7f0766` | `30494f83da9396ef81b855907fd878bf` | `ae8ccd60fbc977970c6cf40a16ee375c` |
| typescript | yes | `636b78e951a658bd1a210a38aa7f0766` | `1647df9a31f922d3467d1754494ae512` | `3a8d451af6dc74383b4aeb9c7111e81a` |
| python | no | `1bf00726d17e1ee5a07c1e87f3cbd854` | `b7642d8451d2d2b4ef4498a40018b7af` | `173f16bec7c66e0dd94f6155487124f6` |
| python | yes | `1bf00726d17e1ee5a07c1e87f3cbd854` | `7822ec6b90ef3a38be7ce47cf442b5e1` | `589e2c8c4cb818165f470113b7415421` |

All four workflows ran exactly one successful cleanup activity and then ended
with the supplied CancelledFailure; both outer runtime tasks exited 0. The
concurrent cases recorded both TimerStarted events before cancellation. No
workflow stayed blocked after cleanup or reported success. Fixture commands
and cleanup procedure are unchanged from above.
