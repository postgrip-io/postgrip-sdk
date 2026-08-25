import { describe, expect, it, vi } from 'vitest';

import { ServiceAPIError, ServiceClient, referenceFor } from '../src/index.js';

const service = {
  ref: 'project:11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  source: 'project',
  facets: [],
  name: 'api',
  slug: 'api',
  kind: 'backend',
  mode: 'deployed',
  status: 'ready',
  workers: [],
  environmentCount: 1,
  capabilities: [],
  createdAt: '2026-08-24T00:00:00Z',
  updatedAt: '2026-08-24T00:00:00Z',
} as const;

function client(fetchImpl: typeof globalThis.fetch): ServiceClient {
  return new ServiceClient({
    baseUrl: 'https://services.example.test',
    token: 'pgwm_test-token',
    fetch: fetchImpl,
  });
}

describe('ServiceClient', () => {
  it('rejects unsafe configuration', () => {
    expect(() => new ServiceClient({ baseUrl: 'http://example.test', token: 'pgwm_token' })).toThrow(/HTTPS/);
    expect(() => new ServiceClient({ baseUrl: 'https://example.test?q=yes', token: 'pgwm_token' })).toThrow(/query/);
    expect(() => new ServiceClient({ baseUrl: 'https://example.test', token: 'bad' })).toThrow(/pgwm_/);
  });

  it('lists with terminal-equivalent filters and bearer auth', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      expect(url.pathname).toBe('/api/v1/services');
      expect(url.searchParams.get('kind')).toBe('backend');
      expect(url.searchParams.get('worker')).toBe('worker-id');
      expect(url.searchParams.get('limit')).toBe('20');
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer pgwm_test-token');
      expect(init?.redirect).toBe('manual');
      return Response.json({ items: [service], nextCursor: '' });
    }) as typeof globalThis.fetch;

    const page = await client(fetchImpl).list({ kind: 'backend', workerId: 'worker-id', limit: 20 });
    expect(page.items[0]?.name).toBe('api');
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('resolves and creates a scoped service client', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith('/resolve')) return Response.json(service);
      expect(url.pathname).toBe(`/api/v1/services/project/${service.id}/status`);
      return Response.json({ service, environments: [] });
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);
    const resolved = await api.resolve('api');
    const status = await api.forService(referenceFor(resolved)).status();
    expect(status.service.ref).toBe(service.ref);
  });

  it('sends deploy body and explicit idempotency key', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      expect(url.pathname).toBe(`/api/v1/services/project/${service.id}/deploy`);
      expect(init?.method).toBe('POST');
      expect(new Headers(init?.headers).get('Idempotency-Key')).toBe('deploy-1');
      expect(JSON.parse(String(init?.body))).toEqual({
        environmentId: 'environment-id', branch: 'main', expectedCommitSha: 'abc123',
      });
      return Response.json({
        status: 'queued', serviceRef: service.ref, environmentId: 'environment-id', deploymentId: 'deployment-id',
        deployment: {
          id: 'deployment-id', projectId: service.id, environmentId: 'environment-id', commitSha: 'abc123',
          branch: 'main', triggerKind: 'manual', status: 'queued', isCurrent: false,
          createdAt: '2026-08-24T00:00:00Z', updatedAt: '2026-08-24T00:00:00Z',
        },
        receipt: { requestId: 'request-id', auditRecorded: true, replayed: false },
      }, { status: 201 });
    }) as typeof globalThis.fetch;

    const result = await client(fetchImpl).deploy(service.id, {
      environmentId: 'environment-id', branch: 'main', expectedCommitSha: 'abc123', idempotencyKey: 'deploy-1',
    });
    expect(result.deploymentId).toBe('deployment-id');
  });

  it('rejects invalid idempotency keys before fetching', () => {
    const fetchImpl = vi.fn() as unknown as typeof globalThis.fetch;
    const api = client(fetchImpl);
    expect(() => api.cancel(service.id, 'deployment-id', { idempotencyKey: 'contains space' })).toThrow(/visible ASCII/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('paginates with opaque cursors', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const cursor = new URL(String(input)).searchParams.get('cursor');
      return Response.json({ items: [], nextCursor: cursor ? '' : 'next' });
    }) as typeof globalThis.fetch;
    const cursors: string[] = [];
    for await (const page of client(fetchImpl).pages()) cursors.push(page.nextCursor);
    expect(cursors).toEqual(['next', '']);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('follows server cursors and aborts polling', async () => {
    let calls = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      expect(url.searchParams.get('follow')).toBe('true');
      calls += 1;
      if (calls === 1) return Response.json({
        items: [{ kind: 'runtime', message: 'ready' }], nextCursor: 'next', pollAfterMs: 1,
      });
      expect(url.searchParams.get('cursor')).toBe('next');
      return Response.json({ items: [], nextCursor: 'next', pollAfterMs: 60_000 });
    }) as typeof globalThis.fetch;
    const controller = new AbortController();
    const iterator = client(fetchImpl).logs.follow(referenceFor(service), { signal: controller.signal });
    expect((await iterator.next()).value?.message).toBe('ready');
    const pending = iterator.next();
    while (calls < 2) await new Promise((resolve) => setTimeout(resolve, 1));
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('returns a typed safe error without upstream body leakage', async () => {
    const fetchImpl = vi.fn(async () => new Response('secret upstream body', {
      status: 502, headers: { 'X-Request-ID': 'request-header' },
    })) as typeof globalThis.fetch;
    const error = await client(fetchImpl).resolve('api').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ServiceAPIError);
    expect(error).toMatchObject({ code: 'HTTP_ERROR', requestId: 'request-header' });
    expect(String(error)).not.toContain('secret');
  });
});
