import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseRetryAfter, PostGripAPIError } from '../../src/internal/transport.js';
import { WorkerAPIError, WorkerClient } from '../../src/worker/index.js';
import type { OpenAPIOperationId } from '../../src/worker/generated/openapi.js';

interface ContractOperation {
  readonly id: OpenAPIOperationId;
  readonly method: string;
  readonly path: string;
  readonly authLane: string;
  readonly safety: string;
  readonly idempotency: string;
  readonly retry: string;
  readonly hasBody: boolean;
}

/** Every Worker operation with the annotations the executor must follow, read from the contract. */
function contractOperations(): ContractOperation[] {
  const spec = JSON.parse(readFileSync(new URL('../../../contracts/worker-openapi.json', import.meta.url), 'utf8')) as {
    paths: Record<string, Record<string, Record<string, unknown>>>;
  };
  const operations: ContractOperation[] = [];
  for (const [path, item] of Object.entries(spec.paths)) {
    for (const [method, operation] of Object.entries(item)) {
      if (typeof operation !== 'object' || operation === null || typeof operation.operationId !== 'string') continue;
      operations.push({
        id: operation.operationId as OpenAPIOperationId,
        method: method.toUpperCase(),
        path,
        authLane: String(operation['x-postgrip-auth-lane']),
        safety: String(operation['x-postgrip-safety']),
        idempotency: String(operation['x-postgrip-idempotency']),
        retry: String(operation['x-postgrip-retry']),
        hasBody: 'requestBody' in operation,
      });
    }
  }
  return operations;
}

interface Recorded {
  readonly url: string;
  readonly method: string;
  readonly headers: Headers;
  readonly redirect: RequestRedirect | undefined;
}

function recordingFetch(responses: Array<() => Response>) {
  const recorded: Recorded[] = [];
  const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    recorded.push({ url: String(input), method: init?.method ?? 'GET', headers: new Headers(init?.headers), redirect: init?.redirect });
    return (responses[Math.min(recorded.length, responses.length) - 1] ?? (() => Response.json({})))();
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, recorded };
}

function callOperation(client: WorkerClient, operation: ContractOperation, idempotencyKey?: string): Promise<unknown> {
  const pathParameters = Object.fromEntries(
    [...operation.path.matchAll(/\{(\w+)\}/g)].map(([, name]) => [name, `p-${name}`]),
  );
  const options = {
    pathParameters,
    ...(operation.hasBody ? { body: {} } : {}),
    ...(idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : {}),
  };
  return client.openapi.request(operation.id, options as never);
}

const busy = () => Response.json({ code: 'BUSY', message: 'busy', requestId: 'req-1' }, { status: 503, headers: { 'Retry-After': '0' } });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Worker executor conformance', () => {
  const operations = contractOperations();

  it('covers every generated Worker operation', () => {
    expect(operations).toHaveLength(18);
  });

  for (const operation of operations) {
    describe(operation.id, () => {
      const key = operation.idempotency === 'required' ? 'key-1' : undefined;
      const eligible = operation.retry === 'bounded' && (operation.safety === 'read-only' || key !== undefined);

      it('applies its auth lane, declared headers and manual redirects', async () => {
        const { fetch, recorded } = recordingFetch([() => Response.json({})]);
        const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch });
        await callOperation(client, operation, key);
        const [request] = recorded;
        expect(request?.method).toBe(operation.method);
        expect(request?.redirect).toBe('manual');
        expect(request?.headers.get('authorization')).toBe(operation.authLane === 'public' ? null : 'Bearer pgt_management');
        expect(request?.headers.get('idempotency-key')).toBe(key ?? null);
        expect(request?.headers.get('content-type')).toBe(operation.hasBody ? 'application/json' : null);
      });

      it(eligible ? 'retries with retries enabled, reusing its key' : 'never retries', async () => {
        const enabled = recordingFetch([busy, () => Response.json({})]);
        const client = new WorkerClient({
          baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch: enabled.fetch, enableRetries: true,
        });
        const outcome = callOperation(client, operation, key);
        if (eligible) {
          await expect(outcome).resolves.toEqual({});
          expect(enabled.recorded).toHaveLength(2);
          expect(enabled.recorded.map((request) => request.headers.get('idempotency-key'))).toEqual([key ?? null, key ?? null]);
        } else {
          await expect(outcome).rejects.toBeInstanceOf(WorkerAPIError);
          expect(enabled.recorded).toHaveLength(1);
        }

        const disabled = recordingFetch([busy, () => Response.json({})]);
        const plain = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch: disabled.fetch });
        await expect(callOperation(plain, operation, key)).rejects.toBeInstanceOf(WorkerAPIError);
        expect(disabled.recorded).toHaveLength(1);
      });

      if (key) {
        it('rejects a missing idempotency key before sending', async () => {
          const { fetch, recorded } = recordingFetch([() => Response.json({})]);
          const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch });
          await expect(callOperation(client, operation)).rejects.toThrow('visible ASCII');
          expect(recorded).toHaveLength(0);
        });
      }
    });
  }

  it('decodes the error envelope into a WorkerAPIError that is a PostGripAPIError', async () => {
    const { fetch } = recordingFetch([() => Response.json(
      { code: 'NOT_FOUND', message: 'worker not found', details: { workerId: 'w' } },
      { status: 404, headers: { 'X-Request-ID': 'req-header' } },
    )]);
    const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch });
    const error = await client.get('w').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(WorkerAPIError);
    expect(error).toBeInstanceOf(PostGripAPIError);
    expect(error).toMatchObject({
      name: 'WorkerAPIError', status: 404, code: 'NOT_FOUND', message: 'worker not found',
      requestId: 'req-header', details: { workerId: 'w' },
    });
  });

  it('returns a redirect as an error without following it', async () => {
    const { fetch, recorded } = recordingFetch([() => new Response(null, { status: 302, headers: { Location: 'https://elsewhere.example.com/' } })]);
    const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch });
    await expect(client.get('w')).rejects.toMatchObject({ status: 302 });
    expect(recorded).toHaveLength(1);
  });

  it('caps Retry-After at 30 seconds and ignores signed values', () => {
    expect(parseRetryAfter('120', 30_000)).toBe(30_000);
    expect(parseRetryAfter('0', 30_000)).toBe(0);
    expect(parseRetryAfter('+5', 30_000)).toBeUndefined();
    expect(parseRetryAfter('-5', 30_000)).toBeUndefined();
    expect(parseRetryAfter(new Date(Date.now() - 1_000).toUTCString(), 30_000)).toBe(0);
  });

  it('bounds each exchange at 30 seconds by default', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch: fetch as unknown as typeof globalThis.fetch });
    const pending = client.get('w').catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(29_999);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });

  it('keeps the timeout as the failure when an error body stalls', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => new Response(
      new ReadableStream({
        start(controller) {
          init?.signal?.addEventListener('abort', () => controller.error(init.signal?.reason));
        },
      }),
      { status: 500 },
    ));
    const client = new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', fetch: fetch as unknown as typeof globalThis.fetch });
    const pending = client.get('w').catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(30_000);
    const error = await pending;
    expect(error).not.toBeInstanceOf(WorkerAPIError);
    expect(error).toMatchObject({ name: 'TimeoutError' });
  });

  it('lets an earlier caller abort win over the timeout', async () => {
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_management', timeoutMs: 60_000,
      fetch: fetch as unknown as typeof globalThis.fetch,
    });
    const controller = new AbortController();
    const pending = client.get('w', { signal: controller.signal });
    const reason = new Error('caller cancelled');
    controller.abort(reason);
    await expect(pending).rejects.toBe(reason);
  });

  it('rejects a non-positive timeout or one the platform timer would overflow', () => {
    for (const timeoutMs of [0, -1, Number.NaN, 2_147_483_648, Number.POSITIVE_INFINITY]) {
      expect(() => new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', timeoutMs }))
        .toThrow('timeoutMs');
    }
    expect(() => new WorkerClient({ baseUrl: 'https://workers.example.com', token: 'pgt_management', timeoutMs: 2_147_483_647 }))
      .not.toThrow();
  });
});
