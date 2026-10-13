# Installation

```sh
npm install @postgrip/sdk
```

Or with another package manager:

```sh
pnpm add @postgrip/sdk
yarn add @postgrip/sdk
bun add @postgrip/sdk
```

To pin a specific version:

```sh
npm install @postgrip/sdk@0.13.0
```

## Requirements

- **Node.js 20 or newer** (or Bun ≥ 1.0). The SDK is published as ESM only — `"type": "module"` in `package.json`.
- A reachable PostGrip Agent runtime service. The default address is `https://agentorchestrator1.postgrip.io`.

## Importing

The package exposes one root facade and one public entry point per API plane.
Agent runtime names come from `@postgrip/sdk/agent`:

```ts
import {
  Client,
  Connection,
  Agent,
  // workflow runtime
  proxyActivities,
  sleep,
  condition,
  executeChild,
  continueAsNew,
  defineSignal,
  defineQuery,
  defineUpdate,
  setHandler,
  milestone,
  workflowInfo,
  // activity helpers
  activityInfo,
  heartbeat,
  activityMilestone,
  activityStdout,
  activityStderr,
  // errors
  ApplicationFailure,
  CancelledFailure,
  TimeoutFailure,
  TaskFailedError,
} from '@postgrip/sdk/agent';
```

`Agent` is also re-exported as `Worker` if you prefer the Temporal-classic name:

```ts
import { Worker } from '@postgrip/sdk/agent';
```

## ESM only

The package is published as ESM (`"type": "module"`). For CommonJS projects, use a dynamic `import('@postgrip/sdk/agent')` or migrate to ESM. The `.cjs`-only path is not supported.

## TypeScript

The package ships with TypeScript declarations (`dist/index.d.ts`). No `@types/...` package needed.

```ts
import type { WorkflowFunction, ActivityRegistry, RetryPolicy } from '@postgrip/sdk/agent';
```

## Local development from a clone

```sh
git clone https://github.com/postgrip-io/postgrip-sdk.git
cd postgrip-sdk/typescript
bun install --frozen-lockfile
bun run typecheck
bun run build
bun run test
```

Repository development and CI use Bun. The build script itself invokes
`bun run clean`, so invoking `npm run build` still requires Bun. This tooling
requirement is separate from running the published ESM package on Node.

## Running against a local agent

For local development, point the SDK at a runtime service running on your machine:

```ts
import { Connection } from '@postgrip/sdk/agent';

const connection = await Connection.connect({
  baseUrl: 'http://127.0.0.1:4100',
  insecureDevelopment: true, // Explicitly opt in only for local development.
  // Common tenant management token with the required Agent scopes.
  authToken: process.env.POSTGRIP_TOKEN,
});
```

When `baseUrl` is omitted, the connection checks `POSTGRIP_AGENT_URL`, then
`POSTGRIP_URL`, before using the built-in cloud address. For root-facade and
direct-client precedence, see the
[configuration owner](https://github.com/postgrip-io/postgrip-sdk/blob/main/docs/configuration.md).
