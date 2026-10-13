import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { DeterminismError, WorkflowReplay } from '../../src/agent/_replay.js';
import { Agent } from '../../src/agent/agent.js';
import type { Connection } from '../../src/agent/connection.js';
import { ApplicationFailure } from '../../src/agent/errors.js';
import type { Task, WorkflowHistoryEvent } from '../../src/agent/types.js';
import { defineQuery, proxyActivities, setHandler, sleep } from '../../src/agent/workflow.js';

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

  it('fails a diverging workflow task with the public WorkflowDeterminismViolation failure', async () => {
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
        failure: expect.objectContaining({ type: 'WorkflowDeterminismViolation', non_retryable: true }),
      }),
    );
  });
});

interface ReplayFixtureStep {
  command: 'activity' | 'timer' | 'child';
  name?: string;
  duration_ms?: number;
  workflow_type?: string;
  expect: 'replay' | 'new' | 'nondeterministic';
}

const FIXTURES = new URL('../../../test/fixtures/replay/', import.meta.url);

describe('shared replay conformance fixtures', () => {
  for (const file of readdirSync(FIXTURES).filter((name) => name.endsWith('.json')).sort()) {
    it(file, () => {
      const fixture = JSON.parse(readFileSync(new URL(file, FIXTURES), 'utf8')) as {
        history: WorkflowHistoryEvent[];
        steps: ReplayFixtureStep[];
      };
      const replay = new WorkflowReplay(fixture.history);
      for (const [index, step] of fixture.steps.entries()) {
        let outcome: ReplayFixtureStep['expect'];
        try {
          const event = step.command === 'activity'
            ? replay.nextActivity(step.name ?? '')
            : step.command === 'timer'
              ? replay.nextTimer(step.duration_ms)
              : replay.nextChild(step.workflow_type ?? '');
          outcome = event ? 'replay' : 'new';
        } catch (err) {
          expect(err).toBeInstanceOf(DeterminismError);
          outcome = 'nondeterministic';
        }
        expect({ index, outcome }).toEqual({ index, outcome: step.expect });
      }
      const expectsViolation = fixture.steps.some((step) => step.expect === 'nondeterministic');
      expect(replay.determinismError !== undefined).toBe(expectsViolation);
    });
  }
});

describe('workflow runtime replay rules', () => {
  function runtimeConnection(history: WorkflowHistoryEvent[]) {
    return {
      health: vi.fn(async () => ({ status: 'ok' })),
      configureAgentAuth: vi.fn(),
      getWorkflowHistory: vi.fn(async () => history),
      heartbeatTask: vi.fn(async () => ({})),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      failTask: vi.fn(async () => ({})),
      completeTask: vi.fn(async () => ({})),
      blockTask: vi.fn(async () => ({})),
      enqueueTask: vi.fn(async () => ({})),
      getTask: vi.fn(async () => ({})),
    };
  }

  async function runWorkflowTask(connection: ReturnType<typeof runtimeConnection>, workflows: Record<string, (...args: unknown[]) => Promise<unknown>>, type: string): Promise<void> {
    const previous = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    let agent: Agent;
    try {
      agent = await Agent.create({ connection: connection as unknown as Connection, taskQueue: 'default', workflows });
    } finally {
      if (previous == null) delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      else process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previous;
    }
    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask({
      id: 'task-1', namespace: 'default', queue: 'default', type: `workflow:${type}`,
      payload: { workflowType: type, workflowId: 'workflow-1', runId: 'run-1', args: [] },
      state: 'leased', attempt: 1, lease_timeout_seconds: 30,
      created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z',
    } as Task);
  }

  it('fails the task when workflow code catches a determinism violation', async () => {
    const connection = runtimeConnection([scheduled('A')]);
    const { B } = proxyActivities<{ B(): Promise<string> }>();
    async function CatchingWorkflow(): Promise<string> {
      try {
        await B();
      } catch {
        // Ignored on purpose: nondeterminism must still fail the task.
      }
      return 'done';
    }
    await runWorkflowTask(connection, { CatchingWorkflow }, 'CatchingWorkflow');
    expect(connection.completeTask).not.toHaveBeenCalled();
    expect(connection.failTask).toHaveBeenCalledWith(
      'task-1',
      expect.any(String),
      'activity command changed at index 1: history=A replay=B',
      expect.objectContaining({ failure: expect.objectContaining({ type: 'WorkflowDeterminismViolation' }) }),
    );
  });

  it('schedules concurrent new commands one at a time in call order', async () => {
    const connection = runtimeConnection([]);
    const order: string[] = [];
    let releaseFirst!: () => void;
    const firstHeld = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    connection.enqueueTask = vi.fn(async (request: { type: string }) => {
      order.push(`start ${request.type}`);
      if (request.type === 'activity:First') {
        await firstHeld;
      }
      order.push(`end ${request.type}`);
      return {};
    });
    const { First } = proxyActivities<{ First(): Promise<string> }>();
    const { Second } = proxyActivities<{ Second(): Promise<string> }>();
    async function ConcurrentWorkflow(): Promise<unknown> {
      return Promise.all([First(), Second()]);
    }
    const running = runWorkflowTask(connection, { ConcurrentWorkflow }, 'ConcurrentWorkflow');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(order).toEqual(['start activity:First']);
    releaseFirst();
    await running;
    expect(order).toEqual(['start activity:First', 'end activity:First', 'start activity:Second', 'end activity:Second']);
  });

  it('does not schedule a later command after an earlier enqueue fails', async () => {
    const connection = runtimeConnection([]);
    connection.enqueueTask = vi.fn(async (request: { type: string }) => {
      if (request.type === 'activity:First') {
        throw new Error('enqueue rejected');
      }
      return {};
    });
    const { First } = proxyActivities<{ First(): Promise<string> }>();
    const { Second } = proxyActivities<{ Second(): Promise<string> }>();
    async function FailingEnqueueWorkflow(): Promise<unknown> {
      return Promise.all([First(), Second()]);
    }
    await runWorkflowTask(connection, { FailingEnqueueWorkflow }, 'FailingEnqueueWorkflow');
    expect(connection.enqueueTask).toHaveBeenCalledTimes(1);
    expect(connection.enqueueTask).toHaveBeenCalledWith(expect.objectContaining({ type: 'activity:First' }));
  });

  it('keeps call order when an earlier progress event is slower', async () => {
    const connection = runtimeConnection([]);
    const enqueued: string[] = [];
    connection.appendTaskEvent = vi.fn(async (_id: string, _identity: string, event: { message?: string }) => {
      if (event.message === 'scheduling activity First') {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      return { id: 'event-1' };
    });
    connection.enqueueTask = vi.fn(async (request: { type: string }) => {
      enqueued.push(request.type);
      return {};
    });
    const { First } = proxyActivities<{ First(): Promise<string> }>();
    const { Second } = proxyActivities<{ Second(): Promise<string> }>();
    async function SlowEventWorkflow(): Promise<unknown> {
      return Promise.all([First(), Second()]);
    }
    await runWorkflowTask(connection, { SlowEventWorkflow }, 'SlowEventWorkflow');
    expect(enqueued).toEqual(['activity:First', 'activity:Second']);
  });
});

describe('workflow command settlement', () => {
  function connectionWith(overrides: Record<string, unknown>) {
    return {
      health: vi.fn(async () => ({ status: 'ok' })),
      configureAgentAuth: vi.fn(),
      getWorkflowHistory: vi.fn(async () => []),
      heartbeatTask: vi.fn(async () => ({})),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      failTask: vi.fn(async () => ({})),
      completeTask: vi.fn(async () => ({})),
      blockTask: vi.fn(async () => ({})),
      enqueueTask: vi.fn(async () => ({})),
      getTask: vi.fn(async () => ({})),
      ...overrides,
    };
  }

  async function run(connection: ReturnType<typeof connectionWith>, name: string, workflow: (...args: unknown[]) => Promise<unknown>): Promise<void> {
    const previous = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    let agent: Agent;
    try {
      agent = await Agent.create({ connection: connection as unknown as Connection, taskQueue: 'default', workflows: { [name]: workflow } });
    } finally {
      if (previous == null) delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      else process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previous;
    }
    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask({
      id: 'task-1', namespace: 'default', queue: 'default', type: `workflow:${name}`,
      payload: { workflowType: name, workflowId: 'workflow-1', runId: 'run-1', args: [] },
      state: 'leased', attempt: 1, lease_timeout_seconds: 30,
      created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z',
    } as Task);
  }

  it('blocks on a scheduled activity even when its progress event fails', async () => {
    const connection = connectionWith({
      appendTaskEvent: vi.fn(async (_id: string, _identity: string, event: { message?: string }) => {
        if (event.message === 'scheduling activity First') throw new Error('event rejected');
        return { id: 'event-1' };
      }),
    });
    const { First } = proxyActivities<{ First(): Promise<string> }>();
    async function EventFailureWorkflow(): Promise<unknown> {
      return First();
    }
    await run(connection, 'EventFailureWorkflow', EventFailureWorkflow);
    expect(connection.enqueueTask).toHaveBeenCalledWith(expect.objectContaining({ type: 'activity:First' }));
    expect(connection.blockTask).toHaveBeenCalled();
    expect(connection.failTask).not.toHaveBeenCalled();
  });

  it('waits for every started command before blocking the task', async () => {
    const order: string[] = [];
    let releaseSecond!: () => void;
    const secondHeld = new Promise<void>((resolve) => {
      releaseSecond = resolve;
    });
    const connection = connectionWith({
      enqueueTask: vi.fn(async (request: { type: string }) => {
        if (request.type === 'activity:Second') await secondHeld;
        order.push(`enqueued ${request.type}`);
        return {};
      }),
      blockTask: vi.fn(async () => {
        order.push('blocked');
        return {};
      }),
    });
    const { First } = proxyActivities<{ First(): Promise<string> }>();
    const { Second } = proxyActivities<{ Second(): Promise<string> }>();
    async function DrainWorkflow(): Promise<unknown> {
      return Promise.all([First(), Second()]);
    }
    const running = run(connection, 'DrainWorkflow', DrainWorkflow);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(order).toEqual(['enqueued activity:First']);
    releaseSecond();
    await running;
    expect(order).toEqual(['enqueued activity:First', 'enqueued activity:Second', 'blocked']);
  });
});

describe('interaction replay determinism', () => {
  const answer = defineQuery<string>('answer');

  async function runQuery(history: WorkflowHistoryEvent[], workflow: (...args: unknown[]) => Promise<unknown>) {
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      configureAgentAuth: vi.fn(),
      getWorkflow: vi.fn(async () => ({ id: 'workflow-1', run_id: 'run-1', task_id: 'workflow-task-1', queue: 'default' })),
      getTask: vi.fn(async () => ({ id: 'workflow-task-1', payload: { args: [] } })),
      getWorkflowHistory: vi.fn(async () => history),
      heartbeatTask: vi.fn(async () => ({})),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      failTask: vi.fn(async () => ({})),
      completeTask: vi.fn(async () => ({})),
      blockTask: vi.fn(async () => ({})),
      enqueueTask: vi.fn(async () => ({})),
    };
    const previous = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    let agent: Agent;
    try {
      agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: { QueriedWorkflow: workflow },
      });
    } finally {
      if (previous == null) delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      else process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previous;
    }
    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask({
      id: 'query-task-1', namespace: 'default', queue: 'default', type: 'query:QueriedWorkflow',
      payload: { workflowId: 'workflow-1', workflowType: 'QueriedWorkflow', queryName: 'answer', args: [] },
      state: 'leased', attempt: 1, lease_timeout_seconds: 30,
      created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z',
    } as Task);
    return connection;
  }

  function timerStarted(durationMs: number): WorkflowHistoryEvent {
    return {
      id: 'event-timer', workflow_id: 'workflow-1', task_id: 'timer-1', type: 'TimerStarted',
      attributes: { duration_ms: durationMs }, created_at: '2026-10-13T00:00:00Z',
    } as WorkflowHistoryEvent;
  }

  it('fails a query whose replay changes a timer duration, with the violation failure type', async () => {
    async function QueriedWorkflow(): Promise<void> {
      setHandler(answer, () => 'ready');
      await sleep(2000);
    }
    const connection = await runQuery([timerStarted(1000)], QueriedWorkflow);
    expect(connection.completeTask).not.toHaveBeenCalled();
    expect(connection.failTask).toHaveBeenCalledWith(
      'query-task-1',
      expect.any(String),
      expect.stringContaining('timer'),
      expect.objectContaining({ failure: expect.objectContaining({ type: 'WorkflowDeterminismViolation' }) }),
    );
  });

  it('reports the determinism violation when replayed code catches it and throws something else', async () => {
    const { B } = proxyActivities<{ B(): Promise<string> }>();
    async function QueriedWorkflow(): Promise<void> {
      setHandler(answer, () => 'ready');
      try {
        await B();
      } catch {
        throw new Error('unrelated failure');
      }
    }
    const connection = await runQuery([scheduled('A')], QueriedWorkflow);
    expect(connection.failTask).toHaveBeenCalledWith(
      'query-task-1',
      expect.any(String),
      'activity command changed at index 1: history=A replay=B',
      expect.objectContaining({ failure: expect.objectContaining({ type: 'WorkflowDeterminismViolation' }) }),
    );
  });
});
