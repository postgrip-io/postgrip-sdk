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
    createError: ({ status, code, message, requestId, details, retryAfterMs }) =>
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

  it('refuses the agent lane without delegated credentials and unknown lanes before sending', async () => {
    const agent = executor([]);
    await expect(agent.instance.request({ operation: operation({ authLane: 'agent' }) })).rejects.toThrow('delegated runtime credentials');
    expect(agent.fetch).not.toHaveBeenCalled();
    const unknown = executor([]);
    await expect(unknown.instance.request({ operation: operation({ authLane: 'unknown' }) })).rejects.toThrow('unsupported auth lane unknown');
    expect(unknown.fetch).not.toHaveBeenCalled();
  });

  it('sends the management bearer on the either lane without delegated credentials', async () => {
    const { fetch, instance } = executor([() => Response.json({})]);
    await instance.request({ operation: operation({ authLane: 'either' }) });
    const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer pgt_management');
  });

  it('refuses a signed operation without a signer before sending', async () => {
    const { fetch, instance } = executor([]);
    await expect(instance.request({ operation: operation({ signing: 'agent-task-v1' }) })).rejects.toThrow('requires request signing');
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

  it('checks an optional idempotency key only when one is sent and never generates one', async () => {
    const optional = operation({ safety: 'mutation', method: 'POST', idempotency: 'optional', headerParameters: ['Idempotency-Key'] });
    for (const idempotencyKey of [' key ', 'k'.repeat(129), 'k\x7f']) {
      const { fetch, instance } = executor([]);
      await expect(instance.request({ operation: optional, idempotencyKey })).rejects.toThrow('idempotencyKey must contain');
      expect(fetch).not.toHaveBeenCalled();
    }
    const unkeyed = executor([busy, () => Response.json({})]);
    await expect(unkeyed.instance.request({ operation: optional })).rejects.toMatchObject({ status: 503 });
    expect(unkeyed.fetch).toHaveBeenCalledOnce();
    const sent = new Headers((unkeyed.fetch.mock.calls[0] as unknown as [URL, RequestInit])[1].headers);
    expect(sent.has('idempotency-key')).toBe(false);
    const keyed = executor([busy, () => Response.json({ ok: true })]);
    await expect(keyed.instance.request({ operation: optional, idempotencyKey: 'send-1' })).resolves.toEqual({ ok: true });
    expect(keyed.fetch).toHaveBeenCalledTimes(2);
    const retried = new Headers((keyed.fetch.mock.calls[1] as unknown as [URL, RequestInit])[1].headers);
    expect(retried.get('idempotency-key')).toBe('send-1');
  });

  it('never retries the statuses a call excludes, and still retries the others', async () => {
    const unconfirmed = () => Response.json({ code: 'UNCONFIRMED', message: 'unconfirmed' }, { status: 504 });
    const { fetch, instance } = executor([busy, unconfirmed, () => Response.json({})]);
    await expect(instance.request({
      operation: operation({ safety: 'mutation', method: 'POST', idempotency: 'required', headerParameters: ['Idempotency-Key'] }),
      idempotencyKey: 'key-1',
      noRetryStatuses: [504],
    })).rejects.toMatchObject({ status: 504, code: 'UNCONFIRMED' });
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
