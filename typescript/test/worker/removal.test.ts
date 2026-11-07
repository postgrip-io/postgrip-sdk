import { describe, expect, it, vi } from 'vitest';
import {
  WorkerAPIError,
  WorkerClient,
  type OpenAPIRemoveWorkerResponse,
  type OpenAPIWorkerRemovalImpact,
} from '../../src/worker/index.js';

const impact: OpenAPIWorkerRemovalImpact = {
  workerId: '9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11',
  etag: '"worker-removal-5f2c"',
  serviceCount: 2,
  managedVolumeCount: 0,
  unreachableVolumes: [],
  projects: [
    { id: '3c8e2a1f-5b7d-4e9c-a2f0-6d1b8e4c7a93', name: 'storefront', exclusive: true, usesAsDefault: false },
    { id: '7a4d9e2c-1f3b-4c8a-b6e0-2d5f9a1c3e78', name: 'billing', exclusive: false, usesAsDefault: true },
  ],
};

const removed: OpenAPIRemoveWorkerResponse = {
  workerId: '9b1f5c7e-7f0e-4d1c-9f3a-2a8f0d6b4c11',
  shutdownRequested: true,
  deletedServiceCount: 2,
  deletedProjectCount: 1,
  keptProjectCount: 1,
  unassignedEnvironmentCount: 1,
  clearedProjectDefaultCount: 1,
  workerCleanup: { attempted: 4, failed: 0, skipped: 0 },
  receipt: { requestId: 'req_01', auditRecorded: true, replayed: false },
};

function client(fetchMock: ReturnType<typeof vi.fn>, options: { enableRetries?: boolean } = {}) {
  return new WorkerClient({
    baseUrl: 'https://workers.example.com',
    token: 'pgt_test-token',
    fetch: fetchMock as unknown as typeof globalThis.fetch,
    ...options,
  });
}

describe('WorkerClient removal', () => {
  it('reads the removal impact without fences', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/workers/worker-1/removal-impact');
      expect(init?.method ?? 'GET').toBe('GET');
      const headers = new Headers(init?.headers);
      expect(headers.get('authorization')).toBe('Bearer pgt_test-token');
      expect(headers.get('idempotency-key')).toBeNull();
      expect(headers.get('if-match')).toBeNull();
      return Response.json(impact, { headers: { ETag: impact.etag } });
    });
    await expect(client(fetchMock).removalImpact('worker-1')).resolves.toEqual(impact);
  });

  it('removes with both fences and no body', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/workers/worker-1');
      expect(init?.method).toBe('DELETE');
      expect(init?.body).toBeUndefined();
      const headers = new Headers(init?.headers);
      expect(headers.get('idempotency-key')).toBe('remove-1');
      expect(headers.get('if-match')).toBe('"worker-removal-5f2c"');
      expect(headers.get('content-type')).toBeNull();
      return Response.json(removed);
    });
    await expect(client(fetchMock).remove('worker-1', { idempotencyKey: 'remove-1', ifMatch: impact.etag })).resolves.toEqual(removed);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('validates both fences before any request', async () => {
    const fetchMock = vi.fn(async () => Response.json(removed));
    const worker = client(fetchMock);
    for (const options of [
      { idempotencyKey: '', ifMatch: '"impact"' },
      { idempotencyKey: 'has space', ifMatch: '"impact"' },
      { idempotencyKey: 'remove-1', ifMatch: '' },
      { idempotencyKey: 'remove-1', ifMatch: '  ' },
      { idempotencyKey: 'remove-1', ifMatch: '"impact"\r\nX-Injected: 1' },
    ]) {
      expect(() => worker.remove('worker-1', options)).toThrow();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('surfaces a changed impact as a WorkerAPIError without retrying', async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ code: 'PRECONDITION_FAILED', message: 'impact changed', requestId: 'req-412' }, { status: 412 }));
    const error = await client(fetchMock, { enableRetries: true })
      .remove('worker-1', { idempotencyKey: 'remove-1', ifMatch: '"stale"' })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(WorkerAPIError);
    expect((error as WorkerAPIError).status).toBe(412);
    expect((error as WorkerAPIError).code).toBe('PRECONDITION_FAILED');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('forwards If-Match from the generated client only where declared', async () => {
    const seen: (string | null)[] = [];
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      seen.push(new Headers(init?.headers).get('if-match'));
      return Response.json({});
    });
    const worker = client(fetchMock);
    await worker.openapi.removeWorker({
      pathParameters: { workerId: 'worker-1' },
      headers: { 'Idempotency-Key': 'remove-1', 'If-Match': '"impact"' },
    });
    // upgradeWorker declares no If-Match, so a caller-supplied one is dropped.
    await worker.openapi.upgradeWorker({
      pathParameters: { workerId: 'worker-1' },
      headers: { 'Idempotency-Key': 'upgrade-1', 'If-Match': '"impact"' } as { readonly 'Idempotency-Key': string },
    });
    expect(seen).toEqual(['"impact"', null]);
  });
});
