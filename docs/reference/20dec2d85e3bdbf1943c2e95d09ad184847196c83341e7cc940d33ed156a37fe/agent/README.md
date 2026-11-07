# Agent API

Contract digest: `f29550a4e011d59dd76b398bd364f2c39674a0c47c6428d5a2cfdc2e153bf1c3`
Bundle digest: `20dec2d85e3bdbf1943c2e95d09ad184847196c83341e7cc940d33ed156a37fe`

## Agent runtime

- [`appendAgentTaskEvent`](./appendAgentTaskEvent.md) — Append an event to a leased task
- [`blockAgentTask`](./blockAgentTask.md) — Park a leased task until its workflow is signalled
- [`completeAgentTask`](./completeAgentTask.md) — Complete a leased task successfully
- [`failAgentTask`](./failAgentTask.md) — Fail a leased task
- [`heartbeatAgentTask`](./heartbeatAgentTask.md) — Extend a leased task's lease
- [`pollAgentTask`](./pollAgentTask.md) — Long-poll for the next leased task or lifecycle directive
- [`refreshAgentSession`](./refreshAgentSession.md) — Exchange a refresh token for a new agent session

## Namespaces

- [`createNamespace`](./createNamespace.md) — Create a namespace
- [`listNamespaces`](./listNamespaces.md) — List namespaces visible to the caller

## Sandboxes

- [`connectSandboxSession`](./connectSandboxSession.md) — Attach to an interactive session over WebSocket
- [`createSandbox`](./createSandbox.md) — Create a sandbox
- [`createSandboxSession`](./createSandboxSession.md) — Mint a single-use ticket for a sandbox stream
- [`deleteSandbox`](./deleteSandbox.md) — Request sandbox deletion
- [`deleteWorkspace`](./deleteWorkspace.md) — Delete an uploaded workspace
- [`getSandbox`](./getSandbox.md) — Fetch a sandbox
- [`getWorkspace`](./getWorkspace.md) — Fetch an uploaded workspace
- [`listSandboxes`](./listSandboxes.md) — List sandboxes
- [`listWorkspaces`](./listWorkspaces.md) — List uploaded workspaces
- [`startSandbox`](./startSandbox.md) — Request that a sandbox start
- [`stopSandbox`](./stopSandbox.md) — Request that a sandbox stop
- [`uploadWorkspace`](./uploadWorkspace.md) — Upload a workspace archive

## Schedules

- [`backfillSchedule`](./backfillSchedule.md) — Backfill a schedule across a time range
- [`createSchedule`](./createSchedule.md) — Create a schedule
- [`deleteSchedule`](./deleteSchedule.md) — Delete a schedule
- [`getSchedule`](./getSchedule.md) — Fetch a single schedule
- [`listSchedules`](./listSchedules.md) — List schedules
- [`pauseSchedule`](./pauseSchedule.md) — Pause a schedule
- [`triggerSchedule`](./triggerSchedule.md) — Run a schedule immediately
- [`unpauseSchedule`](./unpauseSchedule.md) — Resume a paused schedule
- [`updateSchedule`](./updateSchedule.md) — Update a schedule

## System

- [`health`](./health.md) — Liveness probe
- [`ready`](./ready.md) — Readiness probe with store counts

## Tasks

- [`enqueueTask`](./enqueueTask.md) — Enqueue a task
- [`getTask`](./getTask.md) — Fetch a single task
- [`listTaskEvents`](./listTaskEvents.md) — List a task's event stream
- [`listTaskEventsBatch`](./listTaskEventsBatch.md) — List recent events for multiple tasks
- [`listTasks`](./listTasks.md) — List tasks

## Workflows

- [`cancelWorkflow`](./cancelWorkflow.md) — Request cooperative cancellation of a workflow
- [`countWorkflows`](./countWorkflows.md) — Count workflow executions matching a filter
- [`getWorkflow`](./getWorkflow.md) — Fetch a workflow execution
- [`listWorkflowHistory`](./listWorkflowHistory.md) — List a workflow's history events
- [`listWorkflows`](./listWorkflows.md) — List workflow executions
- [`signalWithStartWorkflow`](./signalWithStartWorkflow.md) — Signal a workflow, starting it first if none is running
- [`signalWorkflow`](./signalWorkflow.md) — Send a signal to a running workflow
- [`terminateWorkflow`](./terminateWorkflow.md) — Forcibly terminate a workflow
