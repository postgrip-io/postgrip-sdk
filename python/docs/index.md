# PostGrip Agent — Python SDK

Run shell commands, container workloads, and durable workflows on the PostGrip Agent runtime service from your Python code.

**Current release:** `0.13.0`

[Quick start →](quickstart.md){ .md-button .md-button--primary }
[GitHub](https://github.com/postgrip-io/postgrip-sdk/tree/main/python){ .md-button }
[PyPI](https://pypi.org/project/postgrip/){ .md-button }

---

## What this is

A Python library that lets you talk to the PostGrip Agent runtime service. You enqueue tasks (shell commands, containers, workflows, schedules) from a `Client`, or you run an `Agent` that picks up tasks and dispatches them to your registered `@workflow.defn` and `@activity.defn` functions.

The shape mirrors the Temporal Python SDK on purpose: workflows are async classes decorated with `@workflow.defn` and `@workflow.run`; activities are plain async functions decorated with `@activity.defn`; the agent registers both and runs the polling loop. If you've used Temporal in Python, the surface should feel immediate.

```python
from postgrip.agent import Client, Agent, activity, workflow


@activity.defn
async def greet(name: str) -> str:
    return f"Hello {name}"


@workflow.defn
class SayHelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(greet, name)
```

## Polyglot

This is the Python member of the three-language SDK family. The single
`postgrip` distribution contains Agent, Worker, and Service clients; its Go and
TypeScript siblings expose the same API planes and wire contracts.

- [Go SDK](https://github.com/postgrip-io/postgrip-sdk/tree/main/go)
- [TypeScript SDK](https://github.com/postgrip-io/postgrip-sdk/tree/main/typescript)
- [Agent protocol](https://github.com/postgrip-io/postgrip-sdk/tree/main/go/protocol) — the shared runtime wire shapes

## Where to next

- [Installation](installation.md) — `pip install` and version requirements.
- [Quick start](quickstart.md) — copy-paste examples for enqueueing tasks and running an agent.
- [Workflow runtime](workflow-runtime.md) — the durable replay model in depth: history cursor, suspension, determinism rules, sandbox, ContinueAsNew.
- [API](api.md) — the public surface re-exported from `postgrip.agent`.
