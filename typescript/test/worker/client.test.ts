import { describe, expect, it, vi } from 'vitest';
import { WorkerAPIError, WorkerClient } from '../../src/worker/index.js';

describe('WorkerClient', () => {
  it('loads the unified Worker environment variables', () => {
    const client = WorkerClient.fromEnv({
      environment: {
        POSTGRIP_URL: 'https://common.example.test',
        POSTGRIP_WORKER_URL: 'https://workers.example.test',
        POSTGRIP_TOKEN: 'pgt_environment',
      },
      fetch: vi.fn() as unknown as typeof globalThis.fetch,
    });
    expect(client).toBeInstanceOf(WorkerClient);
  });

  it('injects the worker bearer and encodes list queries', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toContain('/api/v1/workers?pageSize=25');
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer pgt_test-token');
      expect(init?.redirect).toBe('manual');
      return Response.json({ items: [] });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
      fetch: fetchMock,
    });

    await expect(client.list({ pageSize: 25 })).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('exposes the observed signer runtime returned for a worker', async () => {
    const fetchMock = vi.fn(async () => Response.json({
      items: [{
        id: 'worker-1',
        name: 'worker-east',
        status: 'online',
        trustState: 'trusted',
        createdAt: '2026-08-25T00:00:00Z',
        updatedAt: '2026-08-25T00:00:00Z',
        capabilities: [],
        previewSubdomainEnabled: false,
        autoShutdownOnRemoval: false,
        signerVersion: 2,
        signerRevision: '30a3e4c53a48544f77735398f4784c20279f0ae3',
      }],
    }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
      fetch: fetchMock,
    });

    const page = await client.list();
    expect(page.items[0]).toMatchObject({
      signerVersion: 2,
      signerRevision: '30a3e4c53a48544f77735398f4784c20279f0ae3',
    });
  });

  it('creates a Worker with caller-owned bootstrap material and replay protection', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/workers');
      expect(init?.method).toBe('POST');
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer pgt_test-token');
      expect(new Headers(init?.headers).get('idempotency-key')).toBe('worker-create-1');
      expect(JSON.parse(String(init?.body))).toMatchObject({
        bootstrap: {
          enrollmentKey: 'enrollment-value',
          attestationBootstrapToken: 'attestation-value',
        },
      });
      return Response.json({ worker: {}, bootstrap: {}, etag: 'worker-etag', receipt: {} });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_test-token', fetch: fetchMock,
    });

    await expect(client.create({
      name: 'worker', host: 'https://worker.example.com', autoShutdownOnRemoval: true,
      bootstrap: {
        enrollmentKey: 'enrollment-value',
        attestationBootstrapToken: 'attestation-value',
      },
    }, { idempotencyKey: 'worker-create-1' })).resolves.toMatchObject({ etag: 'worker-etag' });
  });

  it('preserves a configured reverse-proxy base path', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      expect(String(input)).toBe('https://workers.example.com/postgrip/api/v1/workers');
      return Response.json({ items: [] });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com/postgrip/',
      token: 'pgt_test-token',
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
        expectedSignerVersion: 3,
        signerImage: 'signer',
        receipt: { requestId: 'req', auditRecorded: true, replayed: false },
      });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
      fetch: fetchMock,
      enableRetries: true,
    });

    const result = await client.upgrade('worker', { idempotencyKey: 'upgrade-1' });
    expect(result.expectedVersion).toBe(2);
    expect(result.expectedSignerVersion).toBe(3);
    expect(result.signerImage).toBe('signer');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('returns safe typed errors without retrying by default', async () => {
    const fetchMock = vi.fn(async () => Response.json(
      { code: 'WORKER_UNAVAILABLE', message: 'try later', requestId: 'req-1', details: { safe: true } },
      { status: 503, headers: { 'Retry-After': '3' } },
    ));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
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

  it('ignores Retry-After outside rate-limit and service-unavailable responses', async () => {
    vi.useFakeTimers();
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    const randomSpy = vi.spyOn(Math, 'random').mockReturnValue(0.5);
    let calls = 0;
    const fetchMock = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        return Response.json(
          { code: 'BAD_GATEWAY', message: 'retry', requestId: 'req' },
          { status: 502, headers: { 'Retry-After': '30' } },
        );
      }
      return Response.json({ items: [] });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
      fetch: fetchMock,
      enableRetries: true,
      // Distinct from the 30-second Retry-After this test must not honor.
      timeoutMs: 45_000,
    });

    try {
      const pending = client.list();
      await vi.runAllTimersAsync();
      await expect(pending).resolves.toEqual({ items: [] });
      expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 100);
      expect(timeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 30_000);
    } finally {
      randomSpy.mockRestore();
      timeoutSpy.mockRestore();
      vi.useRealTimers();
    }
  });

  it('normalizes non-object error payloads and still retries', async () => {
    const fetchMock = vi.fn(async () => Response.json(null, {
      status: 503,
      statusText: 'Unavailable',
      headers: { 'Retry-After': '0', 'X-Request-ID': 'req-fallback' },
    }));
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com',
      token: 'pgt_test-token',
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
      token: 'pgt_test-token',
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
      token: 'pgt_test-token',
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
      token: 'pgt_test-token',
      fetch: fetchMock,
    });
    const controller = new AbortController();
    const iterator = client.operationalLogs.follow('worker', { signal: controller.signal });
    await expect(iterator.next()).resolves.toMatchObject({ value: { id: 1 }, done: false });
    controller.abort(new Error('cancelled-buffer'));

    await expect(iterator.next()).rejects.toThrow('cancelled-buffer');
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('requires HTTPS and a non-empty opaque worker token', () => {
    expect(() => new WorkerClient({ baseUrl: 'http://example.com', token: 'pgt_token' })).toThrow('HTTPS');
    expect(() => new WorkerClient({ baseUrl: 'https://example.com', token: '   ' })).toThrow('required');
    expect(() => new WorkerClient({ baseUrl: 'https://example.com', token: 'opaque-token' })).not.toThrow();
  });

  it('rejects an oversized response body', async () => {
    const client = new WorkerClient({
      baseUrl: 'https://example.com',
      token: 'opaque-token',
      fetch: vi.fn<typeof fetch>(async () => new Response('x'.repeat((4 << 20) + 1))),
    });

    await expect(client.list()).rejects.toThrow(/too large/);
  });

  it('executes every Worker facade through its canonical route', async () => {
    const seen: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(String(input));
      seen.push(`${init?.method ?? 'GET'} ${url.pathname}`);
      const headers = new Headers(init?.headers);
      if (url.pathname !== '/health') expect(headers.get('authorization')).toBe('Bearer pgt_test-token');
      if (['POST', 'PUT'].includes(init?.method ?? 'GET')) expect(headers.get('idempotency-key')).toBe('operation-1');
      if (url.pathname.endsWith('/operational-logs') || url.pathname.endsWith('/security-logs')) {
        return Response.json({ items: [], nextCursor: '' });
      }
      if (url.pathname.endsWith('/assignments') || url.pathname.endsWith('/jobs') || url.pathname === '/api/v1/workers') {
        return Response.json({ items: [] });
      }
      return Response.json({});
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_test-token', fetch: fetchMock,
    });

    await client.health();
    await client.list();
    await client.get('worker-1');
    await client.assignments('worker-1');
    await client.jobs('worker-1');
    await client.job('worker-1', 'job-1');
    await client.operationalLogs.list('worker-1');
    await client.securityLogs.list('worker-1');
    await client.check('worker-1', { idempotencyKey: 'operation-1' });
    await client.maintenance('worker-1', { idempotencyKey: 'operation-1' });
    await client.resume('worker-1', { idempotencyKey: 'operation-1' });
    await client.upgrade('worker-1', { idempotencyKey: 'operation-1' });
    await client.snapshotStatus('worker-1');
    await client.snapshots('worker-1');
    await client.takeSnapshot('worker-1', { idempotencyKey: 'operation-1' });
    await client.snapshotSettings('worker-1');
    await client.updateSnapshotSettings('worker-1', { enabled: false }, { idempotencyKey: 'operation-1' });

    expect(seen).toEqual([
      'GET /health',
      'GET /api/v1/workers',
      'GET /api/v1/workers/worker-1',
      'GET /api/v1/workers/worker-1/assignments',
      'GET /api/v1/workers/worker-1/jobs',
      'GET /api/v1/workers/worker-1/jobs/job-1',
      'GET /api/v1/workers/worker-1/operational-logs',
      'GET /api/v1/workers/worker-1/security-logs',
      'POST /api/v1/workers/worker-1/check',
      'POST /api/v1/workers/worker-1/maintenance',
      'POST /api/v1/workers/worker-1/maintenance/resume',
      'POST /api/v1/workers/worker-1/upgrade',
      'GET /api/v1/workers/worker-1/snapshot/status',
      'GET /api/v1/workers/worker-1/snapshots',
      'POST /api/v1/workers/worker-1/snapshots',
      'GET /api/v1/workers/worker-1/snapshot/settings',
      'PUT /api/v1/workers/worker-1/snapshot/settings',
    ]);
  });

  it('paginates workers and jobs with opaque server tokens', async () => {
    let workerPage = 0;
    let jobPage = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(String(input));
      if (url.pathname === '/api/v1/workers') {
        workerPage += 1;
        if (workerPage === 2) expect(url.searchParams.get('pageToken')).toBe('worker-next');
        return Response.json({ items: [], nextPageToken: workerPage === 1 ? 'worker-next' : undefined });
      }
      jobPage += 1;
      if (jobPage === 2) expect(url.searchParams.get('pageToken')).toBe('job-next');
      return Response.json({ items: [], nextPageToken: jobPage === 1 ? 'job-next' : undefined });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_test-token', fetch: fetchMock,
    });

    const workerPages = [];
    for await (const page of client.pages()) workerPages.push(page);
    const jobPages = [];
    for await (const page of client.jobPages('worker-1')) jobPages.push(page);

    expect(workerPages).toHaveLength(2);
    expect(jobPages).toHaveLength(2);
  });

  it('deduplicates security log overlap and honors cancellation', async () => {
    let calls = 0;
    const fetchMock = vi.fn(async () => {
      calls += 1;
      return Response.json(calls === 1
        ? { items: [{ id: 1 }], nextCursor: 'first' }
        : { items: [{ id: 1 }, { id: 2 }], nextCursor: 'second' });
    });
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_test-token', fetch: fetchMock,
    });
    const controller = new AbortController();
    const iterator = client.securityLogs.follow('worker-1', { signal: controller.signal });

    await expect(iterator.next()).resolves.toMatchObject({ value: { id: 1 }, done: false });
    await expect(iterator.next()).resolves.toMatchObject({ value: { id: 2 }, done: false });
    controller.abort(new Error('stop-security-follow'));
    await expect(iterator.next()).rejects.toThrow('stop-security-follow');
  });

  it('rejects unsafe URL and idempotency inputs before fetching', async () => {
    expect(() => new WorkerClient({
      baseUrl: 'https://example.com?tenant=other', token: 'pgt_token',
    })).toThrow('query or fragment');
    const fetchMock = vi.fn();
    const client = new WorkerClient({
      baseUrl: 'https://workers.example.com', token: 'pgt_test-token', fetch: fetchMock,
    });
    expect(() => client.check('worker-1', { idempotencyKey: 'contains whitespace' })).toThrow('visible ASCII');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
