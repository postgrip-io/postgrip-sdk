import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { WorkerClient, type OpenAPIStorageDestinationList } from '../../src/worker/index.js';

const destinations: OpenAPIStorageDestinationList = {
  items: [
    {
      id: '0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a',
      name: 'Production backups',
      provider: 'r2',
      bucket: 'pg-backups',
      endpoint: 'https://account.r2.cloudflarestorage.com',
      accountId: 'account',
      prefix: 'postgrip',
      createdAt: '2026-11-01T09:30:00Z',
      updatedAt: '2026-11-01T09:30:00Z',
    },
    {
      id: '7e3f9a1b-2c4d-4e5f-8a6b-9c0d1e2f3a4b',
      name: 'us-east archive',
      provider: 's3',
      bucket: 'acme-worker-snapshots',
      region: 'us-east-1',
      createdAt: '2026-10-20T14:05:12Z',
      updatedAt: '2026-11-03T08:00:00Z',
    },
  ],
};

function client(fetchMock: ReturnType<typeof vi.fn>, options: { enableRetries?: boolean } = {}) {
  return new WorkerClient({
    baseUrl: 'https://workers.example.com',
    token: 'pgt_test-token',
    fetch: fetchMock as unknown as typeof globalThis.fetch,
    ...options,
  });
}

describe('WorkerClient storage destinations', () => {
  it('reads the organization list without a query or idempotency key', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/storage-destinations');
      expect(init?.method ?? 'GET').toBe('GET');
      const headers = new Headers(init?.headers);
      expect(headers.get('authorization')).toBe('Bearer pgt_test-token');
      expect(headers.get('idempotency-key')).toBeNull();
      return Response.json(destinations);
    });
    const list = await client(fetchMock).storageDestinations();
    expect(list).toEqual(destinations);
    // The id is what updateSnapshotSettings takes as storageDestinationId.
    expect(list.items[0]!.id).toBe('0d6c2a4e-8b1f-4c3d-9e7a-5f2b1c0d9e8a');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('answers an empty list', async () => {
    const fetchMock = vi.fn(async () => Response.json({ items: [] }));
    await expect(client(fetchMock).storageDestinations()).resolves.toEqual({ items: [] });
  });

  it('keeps the bounded read retry', async () => {
    let attempts = 0;
    const fetchMock = vi.fn(async () => {
      attempts += 1;
      if (attempts === 1) {
        return Response.json({ code: 'AUTH_UNAVAILABLE', message: 'try again', requestId: 'req' }, { status: 503, headers: { 'Retry-After': '0' } });
      }
      return Response.json(destinations);
    });
    await expect(client(fetchMock, { enableRetries: true }).storageDestinations()).resolves.toEqual(destinations);
    expect(attempts).toBe(2);
  });

  it('honours the caller signal', async () => {
    const controller = new AbortController();
    controller.abort(new Error('caller stopped'));
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      init?.signal?.throwIfAborted();
      return Response.json(destinations);
    });
    await expect(client(fetchMock).storageDestinations({ signal: controller.signal })).rejects.toThrow();
  });

  it('declares exactly the contract fields and no credential', () => {
    const source = readFileSync(new URL('../../src/worker/generated/openapi.ts', import.meta.url), 'utf8');
    const declaration = /^ {2}readonly "StorageDestination": \{\n([\s\S]*?)^ {2}\};$/m.exec(source)?.[1] ?? '';
    const fields = [...declaration.matchAll(/^ {4}"(\w+)"\??:/gm)].map((match) => match[1]);
    expect(fields).toEqual(['id', 'name', 'provider', 'bucket', 'region', 'endpoint', 'accountId', 'prefix', 'createdAt', 'updatedAt']);
  });
});
