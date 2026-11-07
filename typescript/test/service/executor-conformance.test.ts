import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PostGripAPIError } from '../../src/internal/transport.js';
import { ServiceAPIError, ServiceClient } from '../../src/service/index.js';
import type { OpenAPIOperationId } from '../../src/service/generated/openapi.js';

interface ContractOperation {
  readonly id: OpenAPIOperationId;
  readonly method: string;
  readonly path: string;
  readonly safety: string;
  readonly idempotency: string;
  readonly retry: string;
  readonly headers: ReadonlySet<string>;
  readonly hasBody: boolean;
}

type Parameter = { readonly name: string; readonly in: string } | { readonly $ref: string };

/** Every Service operation with the annotations the executor must follow, read from the contract. */
function contractOperations(): ContractOperation[] {
  const spec = JSON.parse(readFileSync(new URL('../../../contracts/service-openapi.json', import.meta.url), 'utf8')) as {
    paths: Record<string, Record<string, unknown>>;
    components: { parameters?: Record<string, { name: string; in: string }> };
  };
  const resolve = (parameter: Parameter) => ('$ref' in parameter
    ? spec.components.parameters?.[parameter.$ref.split('/').at(-1) ?? '']
    : parameter);
  const operations: ContractOperation[] = [];
  for (const [path, item] of Object.entries(spec.paths)) {
    const shared = (item.parameters ?? []) as Parameter[];
    for (const [method, value] of Object.entries(item)) {
      const operation = value as Record<string, unknown>;
      if (typeof operation !== 'object' || operation === null || typeof operation.operationId !== 'string') continue;
      const parameters = [...shared, ...((operation.parameters ?? []) as Parameter[])].map(resolve);
      operations.push({
        id: operation.operationId as OpenAPIOperationId,
        method: method.toUpperCase(),
        path,
        safety: String(operation['x-postgrip-safety']),
        idempotency: String(operation['x-postgrip-idempotency']),
        retry: String(operation['x-postgrip-retry']),
        headers: new Set(parameters.filter((parameter) => parameter?.in === 'header').map((parameter) => parameter?.name ?? '')),
        hasBody: 'requestBody' in operation,
      });
    }
  }
  return operations;
}

interface Recorded {
  readonly method: string;
  readonly headers: Headers;
  readonly redirect: RequestRedirect | undefined;
}

function recordingFetch(responses: Array<() => Response>) {
  const recorded: Recorded[] = [];
  const fetch = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
    recorded.push({ method: init?.method ?? 'GET', headers: new Headers(init?.headers), redirect: init?.redirect });
    return (responses[Math.min(recorded.length, responses.length) - 1] ?? (() => Response.json({})))();
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, recorded };
}

function serviceClient(fetch: typeof globalThis.fetch, enableRetries = false): ServiceClient {
  return new ServiceClient({ baseUrl: 'https://services.example.com', token: 'pgt_management', fetch, enableRetries });
}

function callOperation(client: ServiceClient, operation: ContractOperation, headers: Record<string, string> = {}): Promise<unknown> {
  const pathParameters = Object.fromEntries(
    [...operation.path.matchAll(/\{(\w+)\}/g)].map(([, name]) => [name, `p-${name}`]),
  );
  const options = {
    pathParameters,
    ...(operation.hasBody ? { body: {} } : {}),
    ...(Object.keys(headers).length > 0 ? { headers } : {}),
  };
  return client.openapi.request(operation.id, options as never);
}

const busy = () => Response.json({ code: 'BUSY', message: 'busy', requestId: 'req-1' }, { status: 503, headers: { 'Retry-After': '0' } });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Service executor conformance', () => {
  const operations = contractOperations();

  it('covers every generated Service operation', () => {
    expect(operations).toHaveLength(124);
  });

  for (const operation of operations) {
    describe(operation.id, () => {
      const key = operation.idempotency === 'required' ? 'key-1' : undefined;
      const sent = {
        ...(key ? { 'Idempotency-Key': key } : {}),
        // Offered on every operation; only those declaring If-Match may forward it.
        'If-Match': '"etag-1"',
      };
      const eligible = operation.retry === 'bounded' && (operation.safety === 'read-only' || key !== undefined);

      it('sends the management bearer, declared headers only and manual redirects', async () => {
        const { fetch, recorded } = recordingFetch([() => Response.json({})]);
        await callOperation(serviceClient(fetch), operation, sent);
        const [request] = recorded;
        expect(request?.method).toBe(operation.method);
        expect(request?.redirect).toBe('manual');
        expect(request?.headers.get('authorization')).toBe('Bearer pgt_management');
        expect(request?.headers.get('idempotency-key')).toBe(key && operation.headers.has('Idempotency-Key') ? key : null);
        expect(request?.headers.get('if-match')).toBe(operation.headers.has('If-Match') ? '"etag-1"' : null);
        expect(request?.headers.get('content-type')).toBe(operation.hasBody ? 'application/json' : null);
      });

      it(eligible ? 'retries with retries enabled, reusing its key' : 'never retries', async () => {
        const enabled = recordingFetch([busy, () => Response.json({})]);
        const outcome = callOperation(serviceClient(enabled.fetch, true), operation, sent);
        if (eligible) {
          await expect(outcome).resolves.toEqual({});
          expect(enabled.recorded).toHaveLength(2);
          expect(new Set(enabled.recorded.map((request) => request.headers.get('idempotency-key')))).toHaveLength(1);
        } else {
          await expect(outcome).rejects.toBeInstanceOf(ServiceAPIError);
          expect(enabled.recorded).toHaveLength(1);
        }

        const disabled = recordingFetch([busy, () => Response.json({})]);
        await expect(callOperation(serviceClient(disabled.fetch), operation, sent)).rejects.toBeInstanceOf(ServiceAPIError);
        expect(disabled.recorded).toHaveLength(1);
      });

      if (key) {
        it('rejects a missing idempotency key before sending', async () => {
          const { fetch, recorded } = recordingFetch([() => Response.json({})]);
          await expect(callOperation(serviceClient(fetch), operation)).rejects.toThrow('visible ASCII');
          expect(recorded).toHaveLength(0);
        });
      }
    });
  }

  it('decodes the error envelope into a ServiceAPIError that is a PostGripAPIError', async () => {
    const { fetch } = recordingFetch([() => Response.json(
      { code: 'NOT_FOUND', message: 'service not found', details: { serviceId: 's' } },
      { status: 404, headers: { 'X-Request-ID': 'req-header' } },
    )]);
    const error = await serviceClient(fetch).resolve('api').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ServiceAPIError);
    expect(error).toBeInstanceOf(PostGripAPIError);
    expect(error).toMatchObject({
      name: 'ServiceAPIError', status: 404, code: 'NOT_FOUND', message: 'service not found',
      requestId: 'req-header', details: { serviceId: 's' },
    });
  });

  it('keeps the 4 MiB bound for a screenshot error body', async () => {
    const message = 'A'.repeat((4 << 20) + 4);
    const { fetch } = recordingFetch([() => Response.json({ code: 'FAILED', message }, { status: 500 })]);
    const error = await serviceClient(fetch).administration.diagnostics.screenshot('project-id', 'deployment-id')
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ServiceAPIError);
    expect(error).toMatchObject({ code: 'HTTP_ERROR' });
  });

  it('ignores a signed Retry-After and backs off with jitter', async () => {
    const random = vi.spyOn(Math, 'random').mockReturnValue(0);
    const { fetch, recorded } = recordingFetch([
      () => Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '+5' } }),
      () => Response.json({}),
    ]);
    await expect(serviceClient(fetch, true).resolve('api')).resolves.toEqual({});
    expect(recorded).toHaveLength(2);
    expect(random).toHaveBeenCalled();
  });

  it('bounds each exchange at 30 seconds by default', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const pending = serviceClient(fetch as unknown as typeof globalThis.fetch).resolve('api').catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(29_999);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });

  it('honors a configured timeout', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason));
    }));
    const client = new ServiceClient({
      baseUrl: 'https://services.example.com', token: 'pgt_management', timeoutMs: 45_000,
      fetch: fetch as unknown as typeof globalThis.fetch,
    });
    const pending = client.resolve('api').catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(44_999);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toMatchObject({ name: 'TimeoutError' });
  });

  it('rejects a non-positive timeout or one the platform timer would overflow', () => {
    for (const timeoutMs of [0, -1, Number.NaN, 2_147_483_648]) {
      expect(() => new ServiceClient({ baseUrl: 'https://services.example.com', token: 'pgt_management', timeoutMs }))
        .toThrow('timeoutMs');
    }
  });
});
