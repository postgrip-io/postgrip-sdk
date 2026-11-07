import { describe, expect, it, vi } from 'vitest';
import { Client } from '../../src/agent/client.js';
import { Connection } from '../../src/agent/connection.js';
import { AgentAPIError } from '../../src/agent/errors.js';

interface Recorded {
  readonly path: string;
  readonly headers: Headers;
  readonly body: string | undefined;
}

const session = { agentId: 'agent-1', accessToken: 'delegated-1', accessExpiresAt: '2999-01-01T00:00:00Z', refreshToken: 'refresh-1' };

function recordingClient(respond: (path: string) => Response = () => Response.json({ id: 'task-1' }), managed = false) {
  const recorded: Recorded[] = [];
  const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    recorded.push({ path, headers: new Headers(init?.headers), body: init?.body as string | undefined });
    return respond(path);
  });
  const connection = Connection.create({
    baseUrl: 'http://agent.test',
    insecureDevelopment: true,
    authToken: 'management-token',
    enableRetries: true,
    fetch: fetch as unknown as typeof globalThis.fetch,
    ...(managed ? { agentAuth: session } : {}),
  });
  return { client: new Client({ connection }), connection, recorded };
}

describe('cancelTask', () => {
  it('posts the reason to the cancel path and answers the cancelled task', async () => {
    const cancelled = {
      id: 'task-1',
      state: 'failed',
      error: 'task cancelled: superseded',
      result: { failure: { type: 'TaskCancelled', message: 'superseded', non_retryable: true } },
    };
    const { client, recorded } = recordingClient(() => Response.json(cancelled));
    await expect(client.task.cancel('task-1', 'superseded')).resolves.toEqual(cancelled);
    await client.task.cancel('task-1');
    expect(recorded.map(({ path, body }) => [path, body])).toEqual([
      ['/api/v1/tasks/task-1/cancel', '{"reason":"superseded"}'],
      ['/api/v1/tasks/task-1/cancel', '{}'],
    ]);
    expect(recorded[0]?.headers.get('authorization')).toBe('Bearer management-token');
    expect(recorded[0]?.headers.has('idempotency-key')).toBe(false);
  });

  it('surfaces a finished task as 409 TASK_TERMINAL with its state, answered once', async () => {
    const { connection, recorded } = recordingClient(() => Response.json(
      { code: 'TASK_TERMINAL', message: 'task is already terminal', requestId: 'req-1', details: { state: 'succeeded' } },
      { status: 409 },
    ));
    const error = await connection.cancelTask('task-1').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentAPIError);
    expect(error).toMatchObject({ status: 409, code: 'TASK_TERMINAL', details: { state: 'succeeded' } });
    expect(recorded).toHaveLength(1);
  });
});

describe('optional Idempotency-Key', () => {
  it('is sent on task sends and signals only when the caller gives one', async () => {
    const { client, connection, recorded } = recordingClient((path) => path.endsWith('/signal-with-start')
      ? Response.json({ workflow: { id: 'order-42', type: 'OrderWorkflow' }, task: { id: 'task-9' }, signal: { id: 'evt-1' } })
      : Response.json({ id: 'task-1' }), true);
    await client.task.enqueue({ type: 'noop', idempotencyKey: 'ci-run-4512' });
    await client.task.noop();
    await connection.signalWorkflow('order-42', { name: 'approve' }, { idempotencyKey: 'approve-1' });
    await client.workflow.signalWithStart('OrderWorkflow', { workflowId: 'order-42', signal: 'approve', idempotencyKey: 'approve-2' });
    await connection.openapi.enqueueTask({ body: { type: 'noop' }, headers: { 'Idempotency-Key': 'raw-1' } });
    expect(recorded.map(({ headers }) => headers.get('idempotency-key'))).toEqual(['ci-run-4512', null, 'approve-1', 'approve-2', 'raw-1']);
  });

  it('is checked before sending and makes the send retryable', async () => {
    let attempt = 0;
    const { client, recorded } = recordingClient(() => (attempt++ === 0
      ? Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '0' } })
      : Response.json({ id: 'task-1' })));
    await expect(client.task.enqueue({ type: 'noop', idempotencyKey: 'not valid' })).rejects.toThrow('idempotencyKey must contain');
    expect(recorded).toHaveLength(0);
    await expect(client.task.enqueue({ type: 'noop', idempotencyKey: 'ci-run-4512' })).resolves.toEqual({ id: 'task-1' });
    expect(recorded.map(({ headers }) => headers.get('idempotency-key'))).toEqual(['ci-run-4512', 'ci-run-4512']);
    expect(recorded[1]?.body).toBe(recorded[0]?.body);
  });
});
