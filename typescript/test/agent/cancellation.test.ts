import { describe, expect, it, vi } from 'vitest';
import { Client } from '../../src/agent/client.js';
import { Connection } from '../../src/agent/connection.js';
import { AgentAPIError } from '../../src/agent/errors.js';
import type { Task, TaskEvent } from '../../src/agent/types.js';

const BASE_URL = 'https://agent.example.test';

interface RecordedRequest {
  readonly url: URL;
  readonly init: RequestInit | undefined;
}

function deferred<T = void>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function routedConnection(route: (url: URL, init: RequestInit | undefined) => Response | Promise<Response>, agentAuth?: { refreshToken: string }) {
  const requests: RecordedRequest[] = [];
  const connection = Connection.create({
    baseUrl: BASE_URL,
    agentAuth,
    fetch: vi.fn<typeof fetch>(async (input, init) => {
      const url = new URL(String(input));
      requests.push({ url, init });
      return route(url, init);
    }),
  });
  return { connection, client: new Client({ connection }), requests };
}

/** A response that never arrives unless the request's signal aborts it. */
function untilAborted(init: RequestInit | undefined): Promise<Response> {
  return new Promise((_resolve, reject) => {
    const signal = init?.signal;
    if (!signal) return;
    if (signal.aborted) reject(signal.reason);
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
}

function event(id: string): TaskEvent {
  return { id, task_id: 'task-1', type: 'stdout', created_at: '2026-10-13T00:00:00Z' } as TaskEvent;
}

function task(state: Task['state']): Task {
  return { id: 'task-1', namespace: 'default', queue: 'default', type: 'noop', state } as Task;
}

function paths(requests: readonly RecordedRequest[]): string[] {
  return requests.map((request) => request.url.pathname);
}

describe('Agent request cancellation', () => {
  it('ends watchEvents while the task-ID lookup is pending', async () => {
    const lookup = deferred();
    const { client, requests } = routedConnection((url, init) => {
      if (url.pathname === '/api/v1/workflows/workflow-1') {
        lookup.resolve();
        return untilAborted(init);
      }
      throw new Error(`unexpected request ${url.pathname}`);
    });
    const controller = new AbortController();
    const events = client.workflow.getHandle('workflow-1').watchEvents({ signal: controller.signal });

    const next = events.next();
    await lookup.promise;
    controller.abort();

    await expect(next).resolves.toEqual({ done: true, value: undefined });
    // The exchange signal is linked to the caller's and carries its abort.
    expect(requests[0]?.init?.signal?.aborted).toBe(true);
    expect(paths(requests)).toEqual(['/api/v1/workflows/workflow-1']);
  });

  it('ends watchEvents while getTaskEvents is pending', async () => {
    const pending = deferred();
    const { client, requests } = routedConnection((url, init) => {
      pending.resolve();
      return untilAborted(init);
    });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    const next = events.next();
    await pending.promise;
    controller.abort();

    await expect(next).resolves.toEqual({ done: true, value: undefined });
    expect(paths(requests)).toEqual(['/api/v1/tasks/task-1/events']);
    // The exchange signal is linked to the caller's and carries its abort.
    expect(requests[0]?.init?.signal?.aborted).toBe(true);
  });

  it('ends watchEvents while getTask is pending', async () => {
    const pending = deferred();
    const { client, requests } = routedConnection((url, init) => {
      if (url.pathname === '/api/v1/tasks/task-1/events') return Response.json({ items: [] });
      pending.resolve();
      return untilAborted(init);
    });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    const next = events.next();
    await pending.promise;
    controller.abort();

    await expect(next).resolves.toEqual({ done: true, value: undefined });
    expect(paths(requests)).toEqual(['/api/v1/tasks/task-1/events', '/api/v1/tasks/task-1']);
    // The exchange signal is linked to the caller's and carries its abort.
    expect(requests[1]?.init?.signal?.aborted).toBe(true);
  });

  it('ends watchEvents while the poll delay is pending', async () => {
    const polled = deferred();
    const connection = {
      getTaskEvents: vi.fn(async () => []),
      getTask: vi.fn(async () => {
        polled.resolve();
        return task('leased');
      }),
    };
    const client = new Client({ connection: connection as unknown as Connection });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal, pollIntervalMs: 60_000 });

    const next = events.next();
    await polled.promise;
    await new Promise((resolve) => setImmediate(resolve));
    controller.abort();

    await expect(next).resolves.toEqual({ done: true, value: undefined });
    expect(connection.getTaskEvents).toHaveBeenCalledTimes(1);
    expect(connection.getTask).toHaveBeenCalledTimes(1);
  });

  it('abandons an aborted refresh wait while the shared refresh completes for another caller', async () => {
    const refreshStarted = deferred();
    const refreshResponse = deferred<Response>();
    const { connection, client, requests } = routedConnection((url) => {
      if (url.pathname === '/api/v1/agent/session/refresh') {
        refreshStarted.resolve();
        return refreshResponse.promise;
      }
      if (url.pathname === '/api/v1/tasks/task-2') return Response.json({ ...task('leased'), id: 'task-2' });
      throw new Error(`unexpected request ${url.pathname}`);
    }, { refreshToken: 'refresh-token' });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    const next = events.next();
    await refreshStarted.promise;
    const other = connection.getTask('task-2');
    controller.abort();

    await expect(next).resolves.toEqual({ done: true, value: undefined });
    refreshResponse.resolve(Response.json({
      agentId: 'agent-1',
      accessToken: 'access-token',
      refreshToken: 'refresh-token-2',
      accessExpiresAt: '2999-01-01T00:00:00Z',
    }));
    await expect(other).resolves.toMatchObject({ id: 'task-2' });

    expect(paths(requests)).toEqual(['/api/v1/agent/session/refresh', '/api/v1/tasks/task-2']);
    // The shared refresh is not cancelled by one caller's abort.
    expect(requests[0]?.init?.signal?.aborted).toBe(false);
    expect(new Headers(requests[1]?.init?.headers).get('authorization')).toBe('Bearer access-token');
    await expect(connection.ensureAgentSession()).resolves.toBe(true);
    expect(requests).toHaveLength(2);
  });

  it('yields no buffered watchEvents event after an abort between next calls', async () => {
    const { client, requests } = routedConnection((url) => {
      if (url.pathname === '/api/v1/tasks/task-1/events') {
        return Response.json({ items: [event('event-1'), event('event-2'), event('event-3')] });
      }
      throw new Error(`unexpected request ${url.pathname}`);
    });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    await expect(events.next()).resolves.toMatchObject({ done: false, value: { id: 'event-1' } });
    controller.abort();

    await expect(events.next()).resolves.toEqual({ done: true, value: undefined });
    expect(paths(requests)).toEqual(['/api/v1/tasks/task-1/events']);
  });

  it('throws the abort reason from iterateTaskEvents before a buffered event', async () => {
    const { connection } = routedConnection(() => Response.json({
      items: [event('event-1'), event('event-2')],
      nextCursor: 'next-page',
    }));
    const controller = new AbortController();
    const reason = new Error('stop watching');
    const received: string[] = [];

    const loop = (async () => {
      for await (const item of connection.iterateTaskEvents('task-1', { signal: controller.signal })) {
        received.push(item.id);
        controller.abort(reason);
      }
    })();

    await expect(loop).rejects.toBe(reason);
    expect(received).toEqual(['event-1']);
  });

  it('rejects getTaskEvents with the abort reason during a pending page', async () => {
    const pending = deferred();
    const { connection, requests } = routedConnection((_url, init) => {
      pending.resolve();
      return untilAborted(init);
    });
    const controller = new AbortController();
    const reason = new Error('stop reading');

    const events = connection.getTaskEvents('task-1', { signal: controller.signal });
    await pending.promise;
    controller.abort(reason);

    await expect(events).rejects.toBe(reason);
    // The exchange signal is linked to the caller's and carries its abort.
    expect(requests[0]?.init?.signal?.reason).toBe(reason);
  });

  it('forwards a signal to getWorkflowHistoryPage and getWorkflow requests', async () => {
    const { connection, requests } = routedConnection((url) => url.pathname.endsWith('/history')
      ? Response.json({ items: [] })
      : Response.json({ id: 'workflow-1' }));
    const controller = new AbortController();

    await connection.getWorkflowHistoryPage('workflow-1', { cursor: 'page-2', signal: controller.signal });
    await connection.getWorkflow('workflow-1', { signal: controller.signal });
    expect(requests).toHaveLength(2);
    expect(requests[0]?.url.searchParams.get('cursor')).toBe('page-2');

    // An aborted caller signal reaches both requests before anything is sent.
    const reason = new Error('stop');
    controller.abort(reason);
    await expect(connection.getWorkflowHistoryPage('workflow-1', { signal: controller.signal })).rejects.toBe(reason);
    await expect(connection.getWorkflow('workflow-1', { signal: controller.signal })).rejects.toBe(reason);
    expect(requests).toHaveLength(2);
  });

  it('still rejects watchEvents for an error the abort did not cause', async () => {
    const { client } = routedConnection((url) => url.pathname === '/api/v1/tasks/task-1/events'
      ? Response.json({ items: [] })
      : Response.json({ message: 'task lookup failed' }, { status: 500 }));
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    const error = await events.next().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentAPIError);
    expect(error).toMatchObject({ status: 500 });
    expect((error as Error).message).not.toContain('task lookup failed');
  });

  it('rejects watchEvents for an unrelated failure that settles after the abort', async () => {
    const pending = deferred();
    let fail!: (error: Error) => void;
    // This transport ignores the signal, so its own failure settles after the abort.
    const { client } = routedConnection(() => {
      pending.resolve();
      return new Promise<Response>((_resolve, reject) => {
        fail = reject;
      });
    });
    const controller = new AbortController();
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    const next = events.next();
    await pending.promise;
    controller.abort();
    fail(new TypeError('network down'));

    await expect(next).rejects.toThrow('network down');
  });

  it('stops waiting on a refresh when the signal aborts while the refresh starts', async () => {
    const controller = new AbortController();
    const { client } = routedConnection((url) => {
      if (url.pathname === '/api/v1/agent/session/refresh') {
        controller.abort();
        return new Promise<Response>(() => undefined);
      }
      throw new Error(`unexpected request ${url.pathname}`);
    }, { refreshToken: 'refresh-token' });
    const events = client.task.watchEvents('task-1', { signal: controller.signal });

    await expect(events.next()).resolves.toEqual({ done: true, value: undefined });
  });
});
