import { describe, expect, it, vi } from 'vitest';
import { WorkerAPIError, WorkerClient } from '../src/index.js';

describe('WorkerClient', () => {
  it('injects the worker bearer and encodes list queries', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toContain('/api/v1/workers?pageSize=25');
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer pgwm_test-token');
      expect(init?.redirect).toBe('manual');
      return Response.json({ items: [] });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
    });

    await expect(client.list({ pageSize: 25 })).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('preserves a configured reverse-proxy base path', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      expect(String(input)).toBe('https://workers.example.com/postgrip/api/v1/workers');
      return Response.json({ items: [] });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com/postgrip/',
      token: 'pgwm_test-token',
      fetch: fetchMock,
    });

    await client.list();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('retries an idempotent mutation only when explicitly enabled', async () => {
    let calls = 0;
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('idempotency-key')).toBe('upgrade-1');
      calls += 1;
      if (calls < 3) {
        return Response.json(
          { code: 'BUSY', message: 'busy', requestId: 'req' },
          { status: 503, headers: { 'Retry-After': '0' } },
        );
      }
      return Response.json({
        status: 'queued',
        worker: {},
        lifecycleDirective: 'upgrade',
        expectedVersion: 2,
        workerImage: 'image',
        receipt: { requestId: 'req', auditRecorded: true, replayed: false },
      });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
      enableRetries: true,
    });

    const result = await client.upgrade('worker', { idempotencyKey: 'upgrade-1' });
    expect(result.expectedVersion).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('returns safe typed errors without retrying by default', async () => {
    const fetchMock = vi.fn(async () => Response.json(
      { code: 'WORKER_UNAVAILABLE', message: 'try later', requestId: 'req-1', details: { safe: true } },
      { status: 503, headers: { 'Retry-After': '3' } },
    ));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
    });

    await expect(client.get('worker')).rejects.toMatchObject<WorkerAPIError>({
      status: 503,
      code: 'WORKER_UNAVAILABLE',
      requestId: 'req-1',
      retryAfterMs: 3_000,
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('normalizes non-object error payloads and still retries', async () => {
    const fetchMock = vi.fn(async () => Response.json(null, {
      status: 503,
      statusText: 'Unavailable',
      headers: { 'Retry-After': '0', 'X-Request-ID': 'req-fallback' },
    }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
      enableRetries: true,
    });

    await expect(client.get('worker')).rejects.toMatchObject<WorkerAPIError>({
      status: 503,
      code: 'HTTP_ERROR',
      requestId: 'req-fallback',
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('exposes since on both log surfaces', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(String(input));
      expect(url.searchParams.get('since')).toBe('2026-08-24T12:00:00Z');
      return Response.json({ items: [], nextCursor: 'cursor' });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
    });

    await client.operationalLogs.list('worker', { since: '2026-08-24T12:00:00Z' });
    await client.securityLogs.list('worker', { since: '2026-08-24T12:00:00Z' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('cancels an empty log-follow poll', async () => {
    const fetchMock = vi.fn(async () => Response.json({ items: [], nextCursor: 'cursor' }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
      followIntervalMs: 10_000,
    });
    const controller = new AbortController();
    const iterator = client.operationalLogs.follow('worker', { signal: controller.signal });
    const next = iterator.next();
    controller.abort(new Error('cancelled'));

    await expect(next).rejects.toThrow('cancelled');
  });

  it('cancels before yielding another buffered log entry', async () => {
    const fetchMock = vi.fn(async () => Response.json({
      items: [{ id: 1 }, { id: 2 }],
      nextCursor: 'cursor',
    }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgwm_test-token',
      fetch: fetchMock,
    });
    const controller = new AbortController();
    const iterator = client.operationalLogs.follow('worker', { signal: controller.signal });
    await expect(iterator.next()).resolves.toMatchObject({ value: { id: 1 }, done: false });
    controller.abort(new Error('cancelled-buffer'));

    await expect(iterator.next()).rejects.toThrow('cancelled-buffer');
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('requires HTTPS and the worker token family', () => {
    expect(() => new WorkerClient({ baseUrl: 'http://example.com', token: 'pgwm_token' })).toThrow('HTTPS');
    expect(() => new WorkerClient({ baseUrl: 'https://example.com', token: 'pga_token' })).toThrow('pgwm_');
  });
});
