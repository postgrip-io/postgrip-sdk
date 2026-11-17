/** Real managed-runtime acceptance; requires a disposable native Agent and stage lease.
 * POSTGRIP_URL/POSTGRIP_AGENT_URL/POSTGRIP_TOKEN configure management access.
 * POSTGRIP_TEST_HOST_QUEUE names only the disposable host's queue.
 * POSTGRIP_TEST_BUN and POSTGRIP_TEST_PYTHON are executable paths on that host.
 * Run from the same checkout visible to the native host. Outputs contain no tokens.
 */
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { Client, Connection } from '../../typescript/dist/agent/index.js';

assert.equal(new URL(process.env.POSTGRIP_AGENT_URL).hostname, 'agentorchestrator.postgrip.app', 'stage only');
const hostQueue = process.env.POSTGRIP_TEST_HOST_QUEUE;
assert.ok(hostQueue?.startsWith('disposable-agent-'), 'a disposable host queue is required');
const connection = await Connection.connect({ authToken: process.env.POSTGRIP_TOKEN });
const client = new Client({ connection });
const report = [];
const owned = [];
async function until(read, predicate, description) {
  const end = Date.now() + 90_000;
  while (Date.now() < end) {
    const value = await read();
    if (predicate(value)) return value;
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error(`timed out: ${description}`);
}
try {
  for (const [language, executable, script] of [
    ['typescript', process.env.POSTGRIP_TEST_BUN, 'cancellation-cleanup-runtime.ts'],
    ['python', process.env.POSTGRIP_TEST_PYTHON, 'cancellation_cleanup_runtime.py'],
  ]) {
    assert.ok(executable, `${language} executable must be explicit`);
    const runtime = await client.task.workflowRuntime({ queue: hostQueue, runtimeQueue: hostQueue, command: executable, args: [fileURLToPath(new URL(script, import.meta.url))] });
    owned.push({ runtime: runtime.id });
    const result = await until(() => connection.getTask(runtime.id), t => ['failed', 'succeeded'].includes(t.state), `${language} runtime`);
    const events = await client.task.events(runtime.id);
    report.push({ language, runtime: runtime.id, state: result.state, result: result.result, events });
    if (result.state !== 'succeeded') console.log(JSON.stringify(report, null, 2));
    assert.equal(result.state, 'succeeded', `${language} runtime failed; inspect its task events`);
  }
  console.log(JSON.stringify(report, null, 2));
} finally {
  // Cancel outer runtime tasks to end the host-launched SDK processes even on failure.
  const failures = [];
  for (const resource of owned.reverse()) {
    try {
      const task = await connection.getTask(resource.runtime);
      if (!['failed', 'succeeded'].includes(task.state)) await client.task.cancel(resource.runtime, 'SDK #152 fixture cleanup');
    } catch (error) { failures.push(error); }
  }
  if (failures.length) throw new AggregateError(failures, 'fixture cleanup failed');
}
