import { describe, expect, it, vi } from 'vitest';
import { DeterminismError, WorkflowReplay } from '../../src/agent/_replay.js';
import { Agent } from '../../src/agent/agent.js';
import type { Connection } from '../../src/agent/connection.js';
import { ApplicationFailure } from '../../src/agent/errors.js';
import type { Task, WorkflowHistoryEvent } from '../../src/agent/types.js';
import { proxyActivities } from '../../src/agent/workflow.js';

function scheduled(activityType: string): WorkflowHistoryEvent {
  return {
    id: `event-${activityType}`,
    workflow_id: 'workflow-1',
    task_id: `activity-${activityType}`,
    type: 'ActivityTaskScheduled',
    attributes: { activity_type: activityType },
    created_at: '2026-10-13T00:00:00Z',
  } as WorkflowHistoryEvent;
}

describe('workflow replay ownership', () => {
  it('raises a replay-owned DeterminismError rather than an SDK failure', () => {
    const replay = new WorkflowReplay([scheduled('A')]);
    let caught: unknown;
    try {
      replay.nextActivity('B');
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(DeterminismError);
    expect(caught).not.toBeInstanceOf(ApplicationFailure);
    expect((caught as Error).message).toBe('activity command changed at index 1: history=A replay=B');
  });

  it('fails a diverging workflow task with the public DeterminismViolation failure', async () => {
    const previousManagedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      configureAgentAuth: vi.fn(),
      getWorkflowHistory: vi.fn(async () => [scheduled('A')]),
      heartbeatTask: vi.fn(async () => ({})),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      failTask: vi.fn(async () => ({})),
      completeTask: vi.fn(async () => ({})),
      blockTask: vi.fn(async () => ({})),
      enqueueTask: vi.fn(async () => ({})),
      getTask: vi.fn(async () => ({})),
    };
    const { B } = proxyActivities<{ B(): Promise<string> }>();
    async function DivergingWorkflow(): Promise<string> {
      return B();
    }
    let agent: Agent;
    try {
      agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: { DivergingWorkflow },
      });
    } finally {
      if (previousManagedRuntime == null) {
        delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      } else {
        process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previousManagedRuntime;
      }
    }

    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask({
      id: 'task-1',
      namespace: 'default',
      queue: 'default',
      type: 'workflow:DivergingWorkflow',
      payload: { workflowType: 'DivergingWorkflow', workflowId: 'workflow-1', runId: 'run-1', args: [] },
      state: 'leased',
      attempt: 1,
      lease_timeout_seconds: 30,
      created_at: '2026-10-13T00:00:00Z',
      updated_at: '2026-10-13T00:00:00Z',
    } as Task);

    expect(connection.enqueueTask).not.toHaveBeenCalled();
    expect(connection.failTask).toHaveBeenCalledWith(
      'task-1',
      expect.any(String),
      'activity command changed at index 1: history=A replay=B',
      expect.objectContaining({
        failure: expect.objectContaining({ type: 'DeterminismViolation', non_retryable: true }),
      }),
    );
  });
});
