import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Connection, type ConnectionOptions } from '../../src/agent/connection.js';
import { AgentAPIError, isTerminalTaskMutation } from '../../src/agent/errors.js';
import { HEADER_AGENT_SIGNATURE } from '../../src/agent/_signing_headers.js';
import { resolveOpenAPIOperation, type OpenAPIOperationId } from '../../src/agent/generated/openapi.js';
import { PostGripAPIError } from '../../src/internal/transport.js';
import { PostGrip } from '../../src/index.js';

interface ContractOperation {
  readonly id: OpenAPIOperationId;
  readonly method: string;
  readonly path: string;
  readonly authLane: string;
  readonly safety: string;
  readonly retry: string;
  readonly signing: string;
  readonly hasBody: boolean;
  readonly adapterOnly: boolean;
}

/** Every Agent operation with the annotations the executor must follow, read from the contract. */
function contractOperations(): ContractOperation[] {
  const spec = JSON.parse(readFileSync(new URL('../../../contracts/agent-openapi.json', import.meta.url), 'utf8')) as {
    paths: Record<string, Record<string, Record<string, unknown>>>;
  };
  const operations: ContractOperation[] = [];
  for (const [path, item] of Object.entries(spec.paths)) {
    for (const [method, operation] of Object.entries(item)) {
      if (typeof operation !== 'object' || operation === null || typeof operation.operationId !== 'string') continue;
      const id = operation.operationId as OpenAPIOperationId;
      const resolved = resolveOpenAPIOperation(id, pathParameters(path));
      operations.push({
        id,
        method: method.toUpperCase(),
        path,
        authLane: String(operation['x-postgrip-auth-lane']),
        safety: String(operation['x-postgrip-safety']),
        retry: String(operation['x-postgrip-retry']),
        signing: String(operation['x-postgrip-request-signing'] ?? ''),
        hasBody: 'requestBody' in operation,
        adapterOnly: resolved.streamingRequest || resolved.webSocket,
      });
    }
  }
  return operations;
}

function pathParameters(path: string): Record<string, string> {
  return Object.fromEntries([...path.matchAll(/\{(\w+)\}/g)].map(([, name]) => [name, `p-${name}`]));
}

interface Recorded {
  readonly url: URL;
  readonly method: string;
  readonly headers: Headers;
  readonly signal: AbortSignal | undefined;
}

const freshSession = { agentId: 'agent-1', accessToken: 'delegated-1', accessExpiresAt: '2999-01-01T00:00:00Z', refreshToken: 'refresh-1' };
const signingPrivateKey = Buffer.alloc(32, 7).toString('base64');

/**
 * A connection over a recording fetch that answers scripted responses in order.
 * Session refreshes get a fresh token unless the refresh is the operation under test.
 */
function recordingConnection(responses: Array<() => Response>, options: Partial<ConnectionOptions> = {}, scriptRefresh = false) {
  const recorded: Recorded[] = [];
  const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input));
    recorded.push({ url, method: init?.method ?? 'GET', headers: new Headers(init?.headers), signal: init?.signal ?? undefined });
    if (url.pathname === '/api/v1/agent/session/refresh' && !scriptRefresh) {
      return Response.json({ ...freshSession, accessToken: `delegated-${recorded.length}` });
    }
    return (responses.shift() ?? (() => Response.json({})))();
  });
  const connection = Connection.create({
    baseUrl: 'http://agent.test',
    insecureDevelopment: true,
    authToken: 'management-token',
    fetch: fetch as unknown as typeof globalThis.fetch,
    ...options,
  });
  return { connection, fetch, recorded };
}

function callOperation(connection: Connection, operation: ContractOperation): Promise<unknown> {
  const options = {
    pathParameters: pathParameters(operation.path),
    ...(operation.hasBody ? { body: {} } : {}),
  };
  return connection.openapi.request(operation.id, options as never);
}

const busy = () => Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '0' } });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Agent executor conformance', () => {
  const operations = contractOperations();
  const executed = operations.filter((operation) => !operation.adapterOnly);

  it('covers every Agent operation; the upload and WebSocket stay with their adapters', () => {
    expect(operations).toHaveLength(46);
    expect(operations.filter((operation) => operation.adapterOnly).map((operation) => operation.id).sort())
      .toEqual(['connectSandboxSession', 'uploadWorkspace']);
  });

  for (const operation of executed) {
    describe(operation.id, () => {
      const eligible = operation.retry === 'bounded' && operation.safety === 'read-only' && !operation.signing;

      it('applies its auth lane with delegated credentials configured', async () => {
        const { connection, recorded } = recordingConnection([() => Response.json({})], {
          headers: { Authorization: 'Bearer configured' },
          agentAuth: { ...freshSession, signingPrivateKey },
        });
        await callOperation(connection, operation);
        const request = recorded.at(-1);
        expect(request?.method).toBe(operation.method);
        expect(request?.headers.get('accept')).toBe('application/json');
        const expected = {
          public: null,
          agent: 'Bearer delegated-1',
          either: 'Bearer delegated-1',
          management: 'Bearer configured',
        }[operation.authLane];
        expect(request?.headers.get('authorization')).toBe(expected);
        expect(request?.headers.has(HEADER_AGENT_SIGNATURE)).toBe(Boolean(operation.signing));
      });

      if (operation.authLane !== 'agent') {
        it('uses the management bearer without delegated credentials', async () => {
          const { connection, recorded } = recordingConnection([() => Response.json({})]);
          await callOperation(connection, operation);
          expect(recorded.at(-1)?.headers.get('authorization')).toBe(operation.authLane === 'public' ? null : 'Bearer management-token');
        });
      }

      it(eligible ? 'retries with retries enabled' : 'never retries', async () => {
        const { connection, recorded } = recordingConnection([busy, () => Response.json({})], {
          enableRetries: true,
          agentAuth: { ...freshSession, signingPrivateKey },
        }, operation.id === 'refreshAgentSession');
        const outcome = callOperation(connection, operation);
        if (eligible) {
          await outcome;
          expect(recorded).toHaveLength(2);
        } else {
          await expect(outcome).rejects.toBeInstanceOf(AgentAPIError);
          expect(recorded).toHaveLength(1);
        }
      });
    });
  }

  it('retries exactly the 18 bounded reads when enabled', () => {
    expect(executed.filter((operation) => operation.retry === 'bounded' && operation.safety === 'read-only')).toHaveLength(18);
  });

  it('keeps retries disabled by default', async () => {
    const { connection, recorded } = recordingConnection([busy, () => Response.json({ status: 'ok' })]);
    await expect(connection.health()).rejects.toBeInstanceOf(AgentAPIError);
    expect(recorded).toHaveLength(1);
  });

  it('refreshes a delegated token that expires during the retry backoff before the next attempt', async () => {
    vi.useFakeTimers({ now: Date.parse('2030-01-01T00:00:00Z') });
    const { connection, recorded } = recordingConnection([
      () => Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '5' } }),
      () => Response.json({ items: [] }),
    ], {
      enableRetries: true,
      // Fresh now, but inside the 30-second refresh margin after the backoff.
      agentAuth: { ...freshSession, accessExpiresAt: '2030-01-01T00:00:33Z' },
    });
    const pending = connection.openapi.request('getTask', { pathParameters: { taskId: 'task-1' } } as never);
    await vi.advanceTimersByTimeAsync(5_000);
    await pending;
    expect(recorded.map((request) => request.url.pathname)).toEqual([
      '/api/v1/tasks/task-1',
      '/api/v1/agent/session/refresh',
      '/api/v1/tasks/task-1',
    ]);
    expect(recorded[0]?.headers.get('authorization')).toBe('Bearer delegated-1');
    expect(recorded[2]?.headers.get('authorization')).toBe('Bearer delegated-2');
  });

  it('strips a configured Authorization on the public lane', async () => {
    const { connection, recorded } = recordingConnection([() => Response.json({ status: 'ok' })], {
      headers: { Authorization: 'Bearer configured', 'X-Trace': 'trace-1' },
    });
    await connection.health();
    expect(recorded[0]?.headers.get('authorization')).toBeNull();
    expect(recorded[0]?.headers.get('x-trace')).toBe('trace-1');
  });

  it('raises AgentAPIError whose text names only the request and status', async () => {
    const { connection } = recordingConnection([() => Response.json(
      { code: 'NOT_FOUND', message: 'secret detail', requestId: 'req-1', details: { taskId: 't' } },
      { status: 404 },
    )]);
    const error = await connection.openapi.request('getTask', { pathParameters: { taskId: 't' } } as never)
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentAPIError);
    expect(error).toBeInstanceOf(PostGripAPIError);
    expect(error).toMatchObject({
      name: 'AgentAPIError', status: 404, code: 'NOT_FOUND', requestId: 'req-1', details: { taskId: 't' },
      method: 'GET', route: '/api/v1/tasks/t', message: 'postgrip-agent: "GET" "/api/v1/tasks/t" -> 404 Not Found',
    });
    expect((error as Error).message).not.toContain('secret detail');
    expect((error as AgentAPIError).responseBody).toContain('secret detail');
  });

  it('types a failed workspace upload as AgentAPIError', async () => {
    const { connection } = recordingConnection([() => Response.json({ code: 'TOO_LARGE', message: 'archive secret' }, { status: 413 })]);
    const error = await connection.uploadWorkspace(new Uint8Array([1])).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AgentAPIError);
    expect(error).toMatchObject({ status: 413, code: 'TOO_LARGE', route: '/api/v1/workspaces' });
    expect((error as Error).message).not.toContain('archive secret');
  });

  it('reports a malformed response without its body or a quoting cause', async () => {
    const { connection } = recordingConnection([() => new Response('{"secret": oops', { status: 200 })]);
    const error = await connection.openapi.request('getTask', { pathParameters: { taskId: 't' } } as never)
      .catch((caught: unknown) => caught) as Error;
    expect(error.message).toBe('postgrip-agent: GET /api/v1/tasks/t -> 200 (parse failed)');
    expect(error.cause).toBeUndefined();
    expect(String(error)).not.toContain('oops');
  });

  it('reports a malformed workspace-upload response without its body', async () => {
    const { connection } = recordingConnection([() => new Response('{"secret": oops', { status: 201 })]);
    const error = await connection.uploadWorkspace(new Uint8Array([1])).catch((caught: unknown) => caught) as Error;
    expect(error.message).toBe('postgrip-agent: POST /api/v1/workspaces -> 201 (parse failed)');
    expect(error.cause).toBeUndefined();
  });

  it('rejects a poll aborted while the shared session refresh is pending', async () => {
    let releaseRefresh: (response: Response) => void = () => undefined;
    const fetch = vi.fn((input: string | URL | Request) => new URL(String(input)).pathname === '/api/v1/agent/session/refresh'
      ? new Promise<Response>((resolve) => { releaseRefresh = resolve; })
      : Promise.resolve(Response.json({})));
    const connection = Connection.create({
      baseUrl: 'http://agent.test', insecureDevelopment: true, fetch: fetch as unknown as typeof globalThis.fetch,
      agentAuth: { agentId: 'agent-1', refreshToken: 'refresh-1' },
    });
    const controller = new AbortController();
    const poll = connection.pollTaskResponse({ queue: 'q', agentId: 'agent-1', signal: controller.signal });
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const reason = new Error('stop polling');
    controller.abort(reason);
    await expect(poll).rejects.toBe(reason);
    releaseRefresh(Response.json(freshSession));
  });

  it('detects terminal and unleased task mutations from the 409 envelope', async () => {
    const conflict = (message: string, status = 409) => recordingConnection(
      [() => Response.json({ code: 'CONFLICT', message }, { status })],
      { agentAuth: freshSession },
    ).connection.completeTask('task-1', 'agent-1', {});
    expect(isTerminalTaskMutation(await conflict('task is already terminal').catch((caught: unknown) => caught))).toBe(true);
    expect(isTerminalTaskMutation(await conflict('task is not leased by agent').catch((caught: unknown) => caught))).toBe(true);
    expect(isTerminalTaskMutation(await conflict('workflow exists').catch((caught: unknown) => caught))).toBe(false);
    expect(isTerminalTaskMutation(await conflict('task is already terminal', 500).catch((caught: unknown) => caught))).toBe(false);
  });

  it('detects a mutation of a task cancelled with cancelTask from its TASK_CANCELLED code', async () => {
    const cancelled = (message: string) => recordingConnection(
      [() => Response.json({ code: 'TASK_CANCELLED', message, requestId: 'req-1' }, { status: 409 })],
      { agentAuth: freshSession },
    ).connection.heartbeatTask('task-1', 'agent-1').catch((caught: unknown) => caught);
    expect(isTerminalTaskMutation(await cancelled('task was cancelled: task is already terminal'))).toBe(true);
    expect(isTerminalTaskMutation(await cancelled('cancelled'))).toBe(true);
  });

  it('keeps a 410 poll as a shutdown directive', async () => {
    const { connection } = recordingConnection([() => Response.json({ directive: { reason: 'drain' } }, { status: 410 })], {
      agentAuth: freshSession,
    });
    await expect(connection.pollTaskResponse({ queue: 'q', agentId: 'agent-1', waitSeconds: 1 }))
      .resolves.toEqual({ directive: { reason: 'drain', type: 'shutdown' } });
  });

  it('bounds each exchange at 30 seconds by default', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const connection = Connection.create({ baseUrl: 'http://agent.test', insecureDevelopment: true, fetch: fetch as unknown as typeof globalThis.fetch });
    const pending = connection.health().catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(29_999);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });

  it('gives a long poll its wait plus 30 seconds', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const connection = Connection.create({
      baseUrl: 'http://agent.test', insecureDevelopment: true, fetch: fetch as unknown as typeof globalThis.fetch,
      agentAuth: freshSession,
    });
    const pending = connection.pollTaskResponse({ queue: 'q', agentId: 'agent-1', waitSeconds: 25 }).catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(54_999);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });

  it('passes the root timeout and retry opt-in to the Agent plane', async () => {
    vi.useFakeTimers();
    const requests: string[] = [];
    const fetch = vi.fn((input: string | URL | Request, init?: RequestInit) => {
      requests.push(new URL(String(input)).pathname);
      if (requests.length === 1) {
        return Promise.resolve(Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '0' } }));
      }
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
      });
    });
    const client = new PostGrip({
      baseUrl: 'http://agent.test', token: 'management-token', insecureDevelopment: true,
      enableRetries: true, timeoutMs: 5_000, fetch: fetch as unknown as typeof globalThis.fetch,
    });
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const pending = client.agent.sandbox.list().catch((caught: unknown) => caught);
    // The 503 is retried; each later attempt is bounded at the root's 5 seconds,
    // and a timed-out eligible read is itself retried until attempts run out.
    await vi.advanceTimersByTimeAsync(4_999);
    expect(requests).toEqual(['/api/v1/sandboxes', '/api/v1/sandboxes']);
    // The second attempt times out at 5 seconds; the zero-jitter backoff then starts the third.
    await vi.advanceTimersByTimeAsync(10);
    expect(requests).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(5_000);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });
});
