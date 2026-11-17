/** Host-launched fixture for SDK #152; build typescript/ before submitting. */
import assert from 'node:assert/strict';
import { Agent, Client, CancellationScope, Connection, cancellationRequested, proxyActivities, sleep } from '../../typescript/dist/agent/index.js';

const { auditCancellation } = proxyActivities<{ auditCancellation(id: string): Promise<string> }>({ startToCloseTimeoutMs: 30_000 });
async function CancellationCleanup(id: string): Promise<string> {
  try {
    await sleep(86_400_000);
    return 'expired';
  } finally {
    if (cancellationRequested()) {
      await CancellationScope.nonCancellable(() => auditCancellation(id));
    }
  }
}
const connection = await Connection.connect();
const agent = await Agent.create({
  connection,
  taskQueue: process.env.POSTGRIP_AGENT_TASK_QUEUE!,
  workflows: { CancellationCleanup },
  activities: { auditCancellation: async (id: string) => {
    console.log(JSON.stringify({ audit: id }));
    return `audit:${id}`;
  } },
});
process.on('SIGTERM', () => void agent.shutdown({ timeoutMs: 5000 }));
async function until<T>(read: () => Promise<T>, predicate: (value: T) => boolean): Promise<T> {
  const end = Date.now() + 90_000;
  while (Date.now() < end) {
    const value = await read();
    if (predicate(value)) return value;
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('live cancellation check timed out');
}
await agent.runUntil((async () => {
  const id = `sdk152-typescript-${crypto.randomUUID()}`;
  const handle = await new Client({ connection }).workflow.start('CancellationCleanup', {
    workflowId: id, taskQueue: process.env.POSTGRIP_AGENT_TASK_QUEUE!, args: [id], workflowRunTimeoutMs: 180_000,
  });
  try {
    await until(() => handle.history(), h => h.some(e => e.type === 'TimerStarted'));
    const workflow = await connection.getWorkflow(handle.runId ?? id);
    await until(() => connection.getTask(workflow.task_id), t => t.state === 'blocked');
    await handle.cancel('SDK #152 live cancellation');
    const task = await until(() => connection.getTask(workflow.task_id), t => t.state === 'failed' || t.state === 'succeeded');
    const history = await handle.history();
    assert.equal(task.state, 'failed');
    assert.equal(task.result?.failure?.type, 'CancelledFailure');
    const cleanups = history.filter(e => e.type === 'ActivityTaskScheduled' && e.attributes?.activity_type === 'auditCancellation');
    assert.equal(cleanups.length, 1);
    const cleanup = await connection.getTask(cleanups[0].task_id!);
    assert.equal(cleanup.state, 'succeeded');
    assert.equal(cleanup.result?.value, `audit:${id}`);
    console.log(JSON.stringify({ language: 'typescript', workflowId: id, runId: handle.runId, cleanup: cleanup.id, cleanupResult: cleanup.result?.value, failure: task.result?.failure, historyTypes: history.map(e => e.type) }));
  } finally {
    const execution = await connection.getWorkflow(handle.runId ?? id);
    const task = await connection.getTask(execution.task_id);
    if (!['failed', 'succeeded'].includes(task.state)) await handle.terminate('SDK #152 fixture cleanup');
  }
})());
