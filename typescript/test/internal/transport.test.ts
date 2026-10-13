import { describe, expect, it, vi } from 'vitest';
import { Executor, PostGripAPIError, type TransportOperation } from '../../src/internal/transport.js';

function operation(overrides: Partial<TransportOperation> = {}): TransportOperation {
  return {
    id: 'testOperation',
    method: 'GET',
    path: '/api/v1/test',
    authLane: 'worker-management',
    safety: 'read-only',
    idempotency: 'none',
    retry: 'bounded',
    headerParameters: [],
    streamingRequest: false,
    webSocket: false,
    ...overrides,
  };
}

function executor(responses: Array<() => Response>) {
  const fetch = vi.fn(async () => (responses.shift() ?? (() => Response.json({})))());
  const instance = new Executor({
    plane: 'Test',
    baseUrl: new URL('https://api.example.com'),
    fetch: fetch as unknown as typeof globalThis.fetch,
    managementToken: 'pgt_management',
    retry: { enabled: true, maxAttempts: 3, maxDelayMs: 1, retryAfterMaxDelayMs: 1 },
    timeoutMs: 30_000,
    createError: (status, code, message, requestId, details, retryAfterMs) =>
      new PostGripAPIError(status, code, message, requestId, details, retryAfterMs),
  });
  return { fetch, instance };
}

const busy = () => Response.json({ code: 'BUSY', message: 'busy' }, { status: 503, headers: { 'Retry-After': '0' } });

describe('Executor', () => {
  it('sends the management bearer on every management lane', async () => {
    for (const authLane of ['management', 'worker-management', 'service-management']) {
      const { fetch, instance } = executor([() => Response.json({})]);
      await instance.request({ operation: operation({ authLane }) });
      const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer pgt_management');
    }
  });

  it('rejects lanes that need the Agent credential hook before sending', async () => {
    for (const authLane of ['agent', 'either', 'unknown']) {
      const { fetch, instance } = executor([]);
      await expect(instance.request({ operation: operation({ authLane }) })).rejects.toThrow(`unsupported auth lane ${authLane}`);
      expect(fetch).not.toHaveBeenCalled();
    }
  });

  it('rejects signed operations before sending', async () => {
    const { fetch, instance } = executor([]);
    await expect(instance.request({ operation: operation({ signing: 'agent-task-v1' }) })).rejects.toThrow('protocol adapter');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('never retries a protocol operation, even when annotated as bounded', async () => {
    const { fetch, instance } = executor([busy, () => Response.json({})]);
    await expect(instance.request({ operation: operation({ safety: 'protocol' }), idempotencyKey: 'key-1' }))
      .rejects.toBeInstanceOf(PostGripAPIError);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it('retries an eligible read when retries are enabled', async () => {
    const { fetch, instance } = executor([busy, () => Response.json({ ok: true })]);
    await expect(instance.request({ operation: operation() })).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
