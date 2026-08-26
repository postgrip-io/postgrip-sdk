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
    expect(() => new ServiceClient({ baseUrl: 'https://example.test?', token: 'pgwm_token' })).toThrow(/query/);
    expect(() => new ServiceClient({ baseUrl: 'https://example.test#', token: 'pgwm_token' })).toThrow(/query/);
    expect(() => new ServiceClient({ baseUrl: 'https://example.test', token: 'bad' })).toThrow(/pgwm_/);
    expect(() => new ServiceClient({
      baseUrl: 'https://example.test', token: 'pgwm_token', retry: { maxAttempts: 4 },
    })).toThrow(/maxAttempts/);
  });

  it('loads the documented Service environment variables', () => {
    const api = ServiceClient.fromEnv({
      environment: {
        POSTGRIP_WORKERORCHESTRATOR_URL: 'https://services.example.test',
        POSTGRIP_SERVICE_API_TOKEN: 'pgwm_environment-token',
      },
      fetch: vi.fn() as unknown as typeof globalThis.fetch,
    });
    expect(api).toBeInstanceOf(ServiceClient);
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

  it('keeps retries disabled by default', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 503 })) as typeof globalThis.fetch;
    await expect(client(fetchImpl).resolve('api')).rejects.toBeInstanceOf(ServiceAPIError);
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('caps configured attempts and Retry-After delays', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', {
      status: 503, headers: { 'Retry-After': '30' },
    })) as typeof globalThis.fetch;
    const api = new ServiceClient({
      baseUrl: 'https://services.example.test',
      token: 'pgwm_test-token',
      fetch: fetchImpl,
      enableRetries: true,
      retry: { maxAttempts: 2, retryAfterMaxDelayMs: 1 },
    });
    const error = await api.resolve('api').catch((cause: unknown) => cause);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(error).toMatchObject({ retryAfterMs: 1 });
  });

  it('cancels during retry backoff', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', {
      status: 503, headers: { 'Retry-After': '30' },
    })) as typeof globalThis.fetch;
    const controller = new AbortController();
    const api = new ServiceClient({
      baseUrl: 'https://services.example.test', token: 'pgwm_test-token', fetch: fetchImpl, enableRetries: true,
    });
    const pending = api.resolve('api', { signal: controller.signal });
    while (fetchImpl.mock.calls.length === 0) await new Promise((resolve) => setTimeout(resolve, 1));
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('bounds success and error response bodies', async () => {
    const oversized = 'x'.repeat((4 << 20) + 1);
    const successFetch = vi.fn(async () => new Response(oversized)) as typeof globalThis.fetch;
    await expect(client(successFetch).resolve('api')).rejects.toThrow(/too large/);

    const errorFetch = vi.fn(async () => new Response(oversized, { status: 502 })) as typeof globalThis.fetch;
    const error = await client(errorFetch).resolve('api').catch((cause: unknown) => cause);
    expect(error).toMatchObject({ code: 'HTTP_ERROR' });
    expect(String(error)).not.toContain(oversized.slice(0, 20));
  });

  it('does not follow redirects or forward the bearer', async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.redirect).toBe('manual');
      return new Response('{}', { status: 307, headers: { Location: 'https://other.example.test/' } });
    }) as typeof globalThis.fetch;
    await expect(client(fetchImpl).resolve('api')).rejects.toMatchObject({ status: 307 });
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('maps every stable facade to its canonical operation', async () => {
    const expected = [
      ['GET', '/api/v1/services'],
      ['GET', '/api/v1/services/resolve'],
      ['GET', '/api/v1/services/project/service-id'],
      ['GET', '/api/v1/services/project/service-id/status'],
      ['GET', '/api/v1/services/project/service-id/environments'],
      ['GET', '/api/v1/services/project/service-id/environments/resolve'],
      ['GET', '/api/v1/services/project/service-id/deployments'],
      ['GET', '/api/v1/services/project/service-id/deployments/deployment-id'],
      ['GET', '/api/v1/services/project/service-id/logs'],
      ['POST', '/api/v1/services/project/service-id/check'],
      ['GET', '/api/v1/services/project/service-id/deploy/preview'],
      ['POST', '/api/v1/services/project/service-id/deploy'],
      ['POST', '/api/v1/services/project/service-id/redeploy'],
      ['POST', '/api/v1/services/project/service-id/deployments/deployment-id/cancel'],
      ['POST', '/api/v1/services/project/service-id/deployments/deployment-id/rollback'],
      ['POST', '/api/v1/services/project/service-id/environments/environment-id/start'],
      ['POST', '/api/v1/services/project/service-id/environments/environment-id/stop'],
      ['POST', '/api/v1/services/project/service-id/environments/environment-id/restart'],
    ] as const;
    let index = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect([init?.method, new URL(String(input)).pathname]).toEqual(expected[index]);
      index += 1;
      return Response.json({});
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);
    const ref = { source: 'project', id: 'service-id' } as const;
    const calls: Array<() => Promise<unknown>> = [
      () => api.list(),
      () => api.resolve('api'),
      () => api.get(ref),
      () => api.status(ref),
      () => api.environments(ref),
      () => api.environment('service-id', 'production'),
      () => api.deployments(ref),
      () => api.deployment('service-id', 'deployment-id'),
      () => api.logs.list(ref),
      () => api.check(ref, { idempotencyKey: 'key' }),
      () => api.previewDeploy('service-id'),
      () => api.deploy('service-id', { expectedCommitSha: 'sha', idempotencyKey: 'key' }),
      () => api.redeploy('service-id', { idempotencyKey: 'key' }),
      () => api.cancel('service-id', 'deployment-id', { idempotencyKey: 'key' }),
      () => api.rollback('service-id', 'deployment-id', { idempotencyKey: 'key' }),
      () => api.start('service-id', 'environment-id', { expectedDeploymentId: 'deployment-id', idempotencyKey: 'key' }),
      () => api.stop('service-id', 'environment-id', { expectedDeploymentId: 'deployment-id', idempotencyKey: 'key' }),
      () => api.restart('service-id', 'environment-id', { expectedDeploymentId: 'deployment-id', idempotencyKey: 'key' }),
    ];
    for (const invoke of calls) await invoke();
    expect(index).toBe(expected.length);
  });

  it('groups all 55 administration operations and sends concurrency fences', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(new URL(String(input)).pathname).toBe('/api/v1/services/targets');
      expect(init?.method).toBe('POST');
      const headers = new Headers(init?.headers);
      expect(headers.get('Idempotency-Key')).toBe('attach-1');
      expect(headers.get('If-Match')).toBe('"service-catalog:4"');
      return Response.json({});
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);
    const methodCount = Object.values(api.administration)
      .reduce((count, group) => count + Object.keys(group).length, 0);
    expect(methodCount).toBe(55);
    await api.administration.targets.attach({
      workerId: '11111111-1111-4111-8111-111111111111',
      name: 'database',
      slug: 'database',
      host: 'database.internal',
      port: 5432,
      databaseName: 'app',
      metadata: {},
    }, { idempotencyKey: 'attach-1', ifMatch: '"service-catalog:4"' });
  });

  it('uses per-environment fences instead of If-Match for bulk variable apply', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(new URL(String(input)).pathname).toBe('/api/v1/services/project/project-id/variables/apply');
      expect(init?.method).toBe('POST');
      const headers = new Headers(init?.headers);
      expect(headers.get('Idempotency-Key')).toBe('apply-1');
      expect(headers.get('If-Match')).toBeNull();
      return Response.json({ results: [], receipt: {} });
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);

    await api.administration.variables.apply('project-id', {
      changes: [{
        environmentId: 'environment-id',
        name: 'DATABASE_URL',
        isSecret: true,
        value: 'postgres://example',
        expectedCollectionVersion: 7,
      }],
    }, { idempotencyKey: 'apply-1' });
  });

  it('rejects malformed administration fences before fetching', async () => {
    const fetchImpl = vi.fn() as unknown as typeof globalThis.fetch;
    const api = client(fetchImpl);
    expect(() => api.administration.configurationOperations.retry(
      'operation-id',
      { idempotencyKey: 'retry-1', ifMatch: 'bad\r\netag' },
    )).toThrow(/If-Match/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('executes all 55 administration facades through the authenticated transport', async () => {
    let requestCount = 0;
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requestCount += 1;
      const headers = new Headers(init?.headers);
      expect(headers.get('Authorization')).toBe('Bearer pgwm_test-token');
      if ((init?.method ?? 'GET') !== 'GET') expect(headers.get('Idempotency-Key')).toBe('operation-1');
      return Response.json({});
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);
    const admin = api.administration;
    const body = {} as never;
    const write = { idempotencyKey: 'operation-1', ifMatch: '"etag:1"' };
    const mutation = { idempotencyKey: 'operation-1' };
    const calls: Array<() => Promise<unknown>> = [
      () => admin.targets.attach(body, write),
      () => admin.targets.update('target-1', body, write),
      () => admin.targets.removalImpact('target-1'),
      () => admin.targets.detach('target-1', body, write),
      () => admin.targets.putConnection('target-1', body, write),
      () => admin.targets.clearConnection('target-1', write),
      () => admin.projects.create(body, write),
      () => admin.projects.update('project-1', body, write),
      () => admin.projects.removalImpact('project-1'),
      () => admin.projects.delete('project-1', body, write),
      () => admin.environments.get('project-1', 'environment-1'),
      () => admin.environments.create('project-1', body, write),
      () => admin.environments.update('project-1', 'environment-1', body, write),
      () => admin.environments.previewReassignment('project-1', 'environment-1', body, mutation),
      () => admin.environments.reassign('project-1', 'environment-1', body, write),
      () => admin.environments.removalImpact('project-1', 'environment-1'),
      () => admin.environments.delete('project-1', 'environment-1', body, write),
      () => admin.volumes.list('project-1'),
      () => admin.volumes.create('project-1', body, write),
      () => admin.volumes.get('project-1', 'volume-1'),
      () => admin.volumes.removalImpact('project-1', 'volume-1'),
      () => admin.volumes.delete('project-1', 'volume-1', body, write),
      () => admin.volumes.bind('project-1', 'environment-1', body, write),
      () => admin.volumes.updateBinding('project-1', 'environment-1', 'volume-1', body, write),
      () => admin.volumes.unbind('project-1', 'environment-1', 'volume-1', write),
      () => admin.domains.list('project-1', 'environment-1'),
      () => admin.domains.create('project-1', 'environment-1', body, write),
      () => admin.domains.update('project-1', 'environment-1', 'domain-1', body, write),
      () => admin.domains.delete('project-1', 'environment-1', 'domain-1', write),
      () => admin.variables.list('project-1', 'environment-1'),
      () => admin.variables.create('project-1', 'environment-1', body, write),
      () => admin.variables.update('project-1', 'environment-1', 'variable-1', body, write),
      () => admin.variables.delete('project-1', 'environment-1', 'variable-1', write),
      () => admin.variables.putValue('project-1', 'environment-1', 'variable-1', body, write),
      () => admin.variables.clearValue('project-1', 'environment-1', 'variable-1', write),
      () => admin.variables.apply('project-1', body, mutation),
      () => admin.repositories.get('project-1'),
      () => admin.repositories.update('project-1', body, write),
      () => admin.repositories.putCredential('project-1', 'source-access', body, write),
      () => admin.repositories.clearCredential('project-1', 'source-access', write),
      () => admin.repositories.refreshCredential('project-1', 'source-access', write),
      () => admin.promotions.list('project-1'),
      () => admin.promotions.preview('project-1', body),
      () => admin.promotions.create('project-1', body, mutation),
      () => admin.retention.getBuild('project-1'),
      () => admin.retention.updateBuild('project-1', body, write),
      () => admin.retention.trimBuild('project-1', write),
      () => admin.retention.flushBuild('project-1', write),
      () => admin.retention.getRuntime('project-1'),
      () => admin.retention.updateRuntime('project-1', body, body, write),
      () => admin.retention.trimRuntime('project-1', body, write),
      () => admin.retention.flushRuntime('project-1', body, write),
      () => admin.configurationOperations.list(),
      () => admin.configurationOperations.get('operation-1'),
      () => admin.configurationOperations.retry('operation-1', write),
    ];

    for (const invoke of calls) await invoke();
    expect(requestCount).toBe(55);
  });

  it('paginates environments and deployments and exercises the scoped facade', async () => {
    const counts = { environments: 0, deployments: 0 };
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith('/environments')) {
        counts.environments += 1;
        if (counts.environments === 2) expect(url.searchParams.get('cursor')).toBe('environment-next');
        return Response.json({ items: [], nextCursor: counts.environments === 1 ? 'environment-next' : '' });
      }
      if (url.pathname.endsWith('/deployments')) {
        counts.deployments += 1;
        if (counts.deployments === 2) expect(url.searchParams.get('cursor')).toBe('deployment-next');
        return Response.json({ items: [], nextCursor: counts.deployments === 1 ? 'deployment-next' : '' });
      }
      if (url.pathname.endsWith('/logs')) return Response.json({ items: [], nextCursor: '', pollAfterMs: 1 });
      return Response.json({});
    }) as typeof globalThis.fetch;
    const api = client(fetchImpl);
    const ref = { source: 'project', id: 'project-1' } as const;

    const environmentPages = [];
    for await (const page of api.environmentPages(ref)) environmentPages.push(page);
    const deploymentPages = [];
    for await (const page of api.deploymentPages(ref)) deploymentPages.push(page);
    const scoped = api.forService(ref);
    await scoped.get();
    await scoped.status();
    await scoped.environments();
    await scoped.deployments();
    await scoped.check({ idempotencyKey: 'operation-1' });
    await scoped.logs.list();

    expect(environmentPages).toHaveLength(2);
    expect(deploymentPages).toHaveLength(2);
  });
});
