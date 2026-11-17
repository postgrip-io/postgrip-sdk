import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Agent } from '../../src/agent/agent.js';
import type { Connection } from '../../src/agent/connection.js';
import type { Task, WorkflowHistoryEvent } from '../../src/agent/types.js';
import { CancellationScope, cancellationRequested, defineQuery, executeChild, proxyActivities, setHandler, sleep } from '../../src/agent/workflow.js';

const { prepare, cleanup, work } = proxyActivities<{ prepare(): Promise<void>; cleanup(): Promise<void>; work(): Promise<void> }>();
const status = defineQuery<boolean>('status');
async function ExpiringWorkflow(withPreparation = false, waitFor = 'timer'): Promise<string> {
  setHandler(status, () => true);
  try {
    if (withPreparation) await prepare();
    if (waitFor === 'parallel') await Promise.all([sleep(86_400_000), sleep(86_400_001)]);
    else if (waitFor === 'activity') await work();
    else if (waitFor === 'child') await executeChild('Child');
    else await sleep(86_400_000);
    return 'expired';
  } finally {
    if (cancellationRequested()) await CancellationScope.nonCancellable(() => cleanup());
  }
}
function event(type: string, task_id?: string, attributes = {}): WorkflowHistoryEvent {
  return { type, task_id, attributes } as WorkflowHistoryEvent;
}
const timer = () => event('TimerStarted', 'timer-1', { duration_ms: 86_400_000 });
const cancel = () => event('WorkflowCancellationRequested', undefined, { reason: 'operator cancelled' });
const task = (args: unknown[] = []): Task => ({
  id: 'workflow-task', namespace: 'default', queue: 'default', type: 'workflow:ExpiringWorkflow',
  payload: { workflowType: 'ExpiringWorkflow', workflowId: 'workflow-1', runId: 'run-1', args },
  state: 'leased', lease_timeout_seconds: 30,
}) as Task;
function connection(history: WorkflowHistoryEvent[]) {
  return {
    health: vi.fn(async () => ({ status: 'ok' })), configureAgentAuth: vi.fn(),
    getWorkflowHistory: vi.fn(async () => history), heartbeatTask: vi.fn(async () => ({})),
    appendTaskEvent: vi.fn(async () => ({})), failTask: vi.fn(async () => ({})),
    completeTask: vi.fn(async () => ({})), blockTask: vi.fn(async () => ({})),
    enqueueTask: vi.fn(async () => ({ id: 'cleanup-task' })),
    getTask: vi.fn(async (id: string) => ({ ...task(), id, state: id === 'prepare-task' ? 'succeeded' : 'queued', result: { value: null } })),
    getWorkflow: vi.fn(async () => ({ task_id: 'workflow-task', queue: 'default' })),
  };
}
async function dispatch(c: ReturnType<typeof connection>, t = task(), workflow = ExpiringWorkflow) {
  // Every dispatch uses a new Agent, simulating restart with only durable history.
  const agent = await Agent.create({ connection: c as unknown as Connection, taskQueue: 'default', workflows: { ExpiringWorkflow: workflow } });
  await (agent as unknown as { executeTask(t: Task): Promise<void> }).executeTask(t);
}

describe('cancellation cleanup replay', () => {
  beforeEach(() => vi.stubEnv('POSTGRIP_AGENT_MANAGED_RUNTIME', 'true'));
  afterEach(() => vi.unstubAllEnvs());
  for (const position of ['parallel', 'activity', 'child', 'before timer', 'pending timer', 'timer fired before cancel', 'timer fired after cancel', 'after preparation'] as const) {
    it(`survives cleanup suspension/restart: ${position}`, async () => {
      const history = position === 'parallel' ? [timer(), event('TimerStarted', 'timer-2', { duration_ms: 86_400_001 }), cancel()]
        : position === 'activity' ? [event('ActivityTaskScheduled', 'work-task', { activity_type: 'work' }), cancel()]
        : position === 'child' ? [event('ChildWorkflowExecutionStarted', 'child-task', { workflow_type: 'Child' }), cancel()]
        : position === 'before timer' ? [cancel()]
        : position === 'timer fired before cancel' ? [timer(), event('TimerFired', 'timer-1'), cancel()]
        : position === 'timer fired after cancel' ? [timer(), cancel(), event('TimerFired', 'timer-1')]
        : position === 'after preparation' ? [event('ActivityTaskScheduled', 'prepare-task', { activity_type: 'prepare' }), event('ActivityTaskCompleted', 'prepare-task'), timer(), cancel()]
        : [timer(), cancel()];
      const c = connection(history);
      const t = task([position === 'after preparation', position]);
      await dispatch(c, t);
      expect(c.failTask).not.toHaveBeenCalled();
      expect(c.completeTask).not.toHaveBeenCalled();
      expect(c.enqueueTask).toHaveBeenCalledTimes(1);
      expect(c.enqueueTask).toHaveBeenCalledWith(expect.objectContaining({ type: 'activity:cleanup' }));
      expect(c.blockTask).toHaveBeenCalledTimes(1);
      history.push(event('ActivityTaskScheduled', 'cleanup-task', { activity_type: 'cleanup' }));
      await dispatch(c, t);
      expect(c.failTask).not.toHaveBeenCalled();
      expect(c.completeTask).not.toHaveBeenCalled();
      expect(c.enqueueTask).toHaveBeenCalledTimes(1);
      expect(c.blockTask).toHaveBeenCalledTimes(2);
      history.push(event('ActivityTaskCompleted', 'cleanup-task'));
      c.getTask.mockImplementation(async (id) => ({ ...task(), id, state: 'succeeded', result: { value: null } }));
      await dispatch(c, t);
      expect(c.enqueueTask).toHaveBeenCalledTimes(1);
      expect(c.completeTask).not.toHaveBeenCalled();
      expect(c.failTask).toHaveBeenCalledTimes(1);
      expect(c.failTask).toHaveBeenCalledWith('workflow-task', expect.any(String), 'operator cancelled', expect.objectContaining({ failure: expect.objectContaining({ type: 'CancelledFailure' }) }));
    });
  }
  it('does not clean up on ordinary suspension or completion', async () => {
    const history: WorkflowHistoryEvent[] = [];
    const c = connection(history);
    await dispatch(c);
    expect(c.enqueueTask).toHaveBeenCalledTimes(1);
    expect(c.enqueueTask).toHaveBeenCalledWith(expect.objectContaining({ type: 'timer' }));
    history.push(timer());
    await dispatch(c);
    expect(c.enqueueTask).toHaveBeenCalledTimes(1);
    history.push(event('TimerFired', 'timer-1'));
    await dispatch(c);
    expect(c.enqueueTask).toHaveBeenCalledTimes(1);
    expect(c.failTask).not.toHaveBeenCalled();
    expect(c.completeTask).toHaveBeenCalledWith('workflow-task', expect.any(String), expect.objectContaining({ value: 'expired' }));
  });
  it('does not mask command divergence with cancellation or finally cleanup', async () => {
    const c = connection([event('TimerStarted', 'timer-1', { duration_ms: 1 }), cancel()]);
    await dispatch(c);
    expect(c.enqueueTask).not.toHaveBeenCalled();
    expect(c.failTask).toHaveBeenCalledWith('workflow-task', expect.any(String), expect.stringContaining('timer command changed'), expect.objectContaining({ failure: expect.objectContaining({ type: 'WorkflowDeterminismViolation' }) }));
  });
  it('keeps a query at the cancellation boundary read-only', async () => {
    const c = connection([timer(), cancel()]);
    await dispatch(c, { ...task(), id: 'query-task', type: 'query:ExpiringWorkflow', payload: { workflowId: 'workflow-1', workflowRunId: 'run-1', workflowType: 'ExpiringWorkflow', queryName: 'status', args: [] } } as Task);
    expect(c.enqueueTask).not.toHaveBeenCalled();
    expect(c.failTask).not.toHaveBeenCalled();
    expect(c.completeTask).toHaveBeenCalledTimes(1);
  });
});

describe('cancellation visibility belongs to the executing command owner', () => {
  it('does not observe a later cancellation inside a completed update', async () => {
    const { WorkflowReplay } = await import('../../src/agent/_replay.js');
    const replay = new WorkflowReplay([
      event('WorkflowUpdateAccepted', 'update-1'),
      event('TimerStarted', 'update-timer', { duration_ms: 10 }),
      event('WorkflowUpdateCompleted', 'update-1'),
      timer(), cancel(), event('ActivityTaskScheduled', 'cleanup-task', { activity_type: 'cleanup' }),
    ], { 'update-timer': 'update-1' });
    const restore = replay.enterOwner('update-1', false);
    expect(replay.isCancellationRequested()).toBe(false);
    replay.nextTimer(10);
    expect(replay.isCancellationRequested()).toBe(false);
    restore();
    expect(replay.isCancellationRequested()).toBe(false);
    replay.nextTimer(86_400_000);
    expect(replay.isCancellationRequested()).toBe(true);
    replay.nextActivity('cleanup');
    expect(replay.isCancellationRequested()).toBe(true);
  });
});
