# PostGrip Agent — TypeScript SDK

Run shell commands, container workloads, and durable workflows on the PostGrip Agent runtime service from your TypeScript code.

**Current release:** `0.13.0`

[Quick start →](quickstart.md){ .md-button .md-button--primary }
[GitHub](https://github.com/postgrip-io/postgrip-sdks/tree/main/typescript){ .md-button }
[npm](https://www.npmjs.com/package/@postgrip/sdk){ .md-button }

---

## What this is

A TypeScript library that lets you talk to the PostGrip Agent runtime service. You enqueue tasks (shell commands, containers, workflows, schedules) from a `Client`, or you run an `Agent` that picks up tasks and dispatches them to your registered workflow functions and activities.

The shape mirrors the Temporal TypeScript SDK on purpose: workflows are plain async functions, activities are plain async functions accessed through a typed `proxyActivities<typeof activities>(...)` stub, and the agent registers both and runs the polling loop. If you've used Temporal in TypeScript, the surface should feel immediate.

```ts
import { proxyActivities } from '@postgrip/sdk/agent';

const activities = {
  async greet(name: string): Promise<string> {
    return `hello, ${name}`;
  },
};

const { greet } = proxyActivities<typeof activities>({
  startToCloseTimeoutMs: 10_000,
  retry: { maximumAttempts: 3 },
});

export async function greetingWorkflow(name: string): Promise<string> {
  return greet(name);
}
```

## Polyglot

This is the TypeScript member of the three-language SDK family. The single
`@postgrip/sdk` package contains Agent, Worker, and Service clients; its Go and
Python siblings expose the same API planes and wire contracts.

- [Go SDK](https://github.com/postgrip-io/postgrip-sdks/tree/main/go)
- [Python SDK](https://github.com/postgrip-io/postgrip-sdks/tree/main/python)
- [Agent protocol](https://github.com/postgrip-io/postgrip-sdks/tree/main/go/protocol) — the shared runtime wire shapes

## Where to next

- [Installation](installation.md) — `npm install` and Node version requirements.
- [Quick start](quickstart.md) — copy-paste examples for enqueueing tasks and running an agent.
- [Workflow runtime](workflow-runtime.md) — the durable replay model in depth: history cursor, suspension, determinism rules, sandbox, ContinueAsNew.
- [API](api.md) — the public surface re-exported from `@postgrip/sdk/agent`.
