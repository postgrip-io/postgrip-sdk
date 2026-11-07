import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { WorkerAPIError, WorkerClient } from '../../src/worker/index.js';

const snapshotRun = {
  snapshot: { workerId: 'w', snapshotId: '20261107T101500.000Z', size: 1, degraded: false, skipped: [] },
  receipt: { requestId: 'req', auditRecorded: true, replayed: false },
};

function client(fetchMock: ReturnType<typeof vi.fn>, options: { enableRetries?: boolean; timeoutMs?: number } = {}) {
  return new WorkerClient({
    baseUrl: 'https://workers.example.com',
    token: 'pgt_test-token',
    fetch: fetchMock as unknown as typeof globalThis.fetch,
    ...options,
  });
}

function refusal(status: number, code: string, headers: Record<string, string> = {}) {
  return () => Response.json({ code, message: 'refused', requestId: 'req' }, { status, headers });
}

/** Resolves after `delayMs` unless the request's signal aborts first. */
function delayed(delayMs: number, response: () => Response) {
  return vi.fn((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
    const timer = setTimeout(() => resolve(response()), delayMs);
    init?.signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(init.signal?.reason);
    }, { once: true });
  }));
}

/** The generated Worker component declarations, by name, as source text. */
function generatedComponents(): Map<string, string> {
  const source = readFileSync(new URL('../../src/worker/generated/openapi.ts', import.meta.url), 'utf8');
  const components = new Map<string, string>();
  for (const match of source.matchAll(/^ {2}readonly "(\w+)": \{\n([\s\S]*?)^ {2}\};$/gm)) {
    components.set(match[1]!, match[2]!);
  }
  return components;
}

/** The components a declaration reaches through `OpenAPIComponents["…"]` references. */
function reachable(components: Map<string, string>, root: string): Set<string> {
  const seen = new Set<string>();
  const pending = [root];
  while (pending.length > 0) {
    const name = pending.pop()!;
    if (seen.has(name)) continue;
    seen.add(name);
    for (const reference of (components.get(name) ?? '').matchAll(/OpenAPIComponents\["(\w+)"\]/g)) pending.push(reference[1]!);
  }
  return seen;
}

describe('WorkerClient snapshots', () => {
  it('refuses a missing or invalid idempotency key on both mutations before fetching', async () => {
    const fetchMock = vi.fn();
    const worker = client(fetchMock);
    for (const idempotencyKey of ['', 'has space', 'k'.repeat(129), undefined as unknown as string]) {
      expect(() => worker.takeSnapshot('w', { idempotencyKey })).toThrow('visible ASCII');
      expect(() => worker.updateSnapshotSettings('w', { enabled: false }, { idempotencyKey })).toThrow('visible ASCII');
      await expect(worker.openapi.createWorkerSnapshot({ pathParameters: { workerId: 'w' }, headers: { 'Idempotency-Key': idempotencyKey } }))
        .rejects.toThrow('visible ASCII');
      await expect(worker.openapi.updateWorkerSnapshotSettings({
        pathParameters: { workerId: 'w' }, headers: { 'Idempotency-Key': idempotencyKey }, body: { enabled: false },
      })).rejects.toThrow('visible ASCII');
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('takes a snapshot with the caller key and decodes the run', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/workers/w/snapshots');
      expect(init?.method).toBe('POST');
      expect(new Headers(init?.headers).get('idempotency-key')).toBe('snapshot-1');
      return Response.json(snapshotRun, { status: 201 });
    });
    await expect(client(fetchMock).takeSnapshot('w', { idempotencyKey: 'snapshot-1' })).resolves.toEqual(snapshotRun);
  });

  it('never retries 504 SNAPSHOT_UNCONFIRMED or 502 SNAPSHOT_FAILED, through either surface', async () => {
    for (const [status, code] of [[504, 'SNAPSHOT_UNCONFIRMED'], [502, 'SNAPSHOT_FAILED']] as const) {
      const fetchMock = vi.fn(async () => refusal(status, code)());
      const worker = client(fetchMock, { enableRetries: true });
      await expect(worker.takeSnapshot('w', { idempotencyKey: 'snapshot-1' })).rejects.toMatchObject({ status, code });
      expect(fetchMock).toHaveBeenCalledOnce();
      await expect(worker.openapi.createWorkerSnapshot({
        pathParameters: { workerId: 'w' }, headers: { 'Idempotency-Key': 'snapshot-1' },
      })).rejects.toBeInstanceOf(WorkerAPIError);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    }
  });

  it('keeps the bounded retry of a 504 on the snapshot reads', async () => {
    const fetchMock = vi.fn(async () => refusal(504, 'GATEWAY_TIMEOUT')());
    await expect(client(fetchMock, { enableRetries: true }).snapshotStatus('w')).rejects.toMatchObject({ status: 504 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('still retries a rate-limited snapshot with the same key', async () => {
    const responses = [refusal(429, 'RATE_LIMITED', { 'Retry-After': '0' }), () => Response.json(snapshotRun, { status: 201 })];
    const fetchMock = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('idempotency-key')).toBe('snapshot-1');
      return responses.shift()!();
    });
    await expect(client(fetchMock, { enableRetries: true }).takeSnapshot('w', { idempotencyKey: 'snapshot-1' })).resolves.toEqual(snapshotRun);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('exposes Retry-After on SNAPSHOT_IN_PROGRESS without retrying it', async () => {
    const fetchMock = vi.fn(async () => refusal(409, 'SNAPSHOT_IN_PROGRESS', { 'Retry-After': '30' })());
    const error = await client(fetchMock, { enableRetries: true }).takeSnapshot('w', { idempotencyKey: 'snapshot-1' }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(WorkerAPIError);
    expect(error).toMatchObject({ status: 409, code: 'SNAPSHOT_IN_PROGRESS', retryAfterMs: 30_000 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('gives a snapshot run a lifetime beyond the configured timeout, which other calls keep', async () => {
    const run = delayed(150, () => Response.json(snapshotRun, { status: 201 }));
    await expect(client(run, { timeoutMs: 50 }).takeSnapshot('w', { idempotencyKey: 'snapshot-1' })).resolves.toEqual(snapshotRun);
    const read = delayed(150, () => Response.json({}));
    await expect(client(read, { timeoutMs: 50 }).snapshotStatus('w')).rejects.toMatchObject({ name: 'TimeoutError' });
  });

  it('allows a snapshot run more than the server\'s 5-minute wait, and a caller abort still wins', async () => {
    vi.useFakeTimers();
    try {
      const run = delayed(5 * 60_000 + 30_000, () => Response.json(snapshotRun, { status: 201 }));
      const pending = client(run).takeSnapshot('w', { idempotencyKey: 'snapshot-1' });
      await vi.advanceTimersByTimeAsync(5 * 60_000 + 30_000);
      await expect(pending).resolves.toEqual(snapshotRun);

      const never = delayed(10 * 60_000, () => Response.json(snapshotRun, { status: 201 }));
      const timedOut = client(never).takeSnapshot('w', { idempotencyKey: 'snapshot-2' }).catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(6 * 60_000);
      expect(await timedOut).toMatchObject({ name: 'TimeoutError' });

      const controller = new AbortController();
      const aborted = client(never).takeSnapshot('w', { idempotencyKey: 'snapshot-3', signal: controller.signal }).catch((e: unknown) => e);
      controller.abort(new Error('caller abort'));
      expect(await aborted).toMatchObject({ message: 'caller abort' });
    } finally {
      vi.useRealTimers();
    }
  });

  it('sends signingKey only when given, and no answer type carries it', async () => {
    const bodies: Record<string, unknown>[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      expect(String(input)).toBe('https://workers.example.com/api/v1/workers/w/snapshot/settings');
      expect(init?.method).toBe('PUT');
      expect(new Headers(init?.headers).get('idempotency-key')).toBe('settings-1');
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return Response.json({
        settings: { workerId: 'w', enabled: true, volumesEnabled: false, volumesHot: false, hasSigningKey: true },
        receipt: { requestId: 'req', auditRecorded: true, replayed: false },
      });
    });
    const worker = client(fetchMock);
    const saved = await worker.updateSnapshotSettings('w', { enabled: true, signingKey: 'base64-seed' }, { idempotencyKey: 'settings-1' });
    expect(saved.settings.hasSigningKey).toBe(true);
    await worker.updateSnapshotSettings('w', { enabled: false }, { idempotencyKey: 'settings-1' });
    expect(bodies[0]).toEqual({ enabled: true, signingKey: 'base64-seed' });
    expect(bodies[1]).toEqual({ enabled: false });

    const components = generatedComponents();
    const carriers = [...components].filter(([, body]) => body.includes('"signingKey"')).map(([name]) => name);
    expect(carriers).toEqual(['UpdateWorkerSnapshotSettingsRequest']);
    for (const response of [
      'WorkerSnapshotStatus', 'WorkerSnapshotList', 'CreateWorkerSnapshotResponse',
      'WorkerSnapshotSettings', 'UpdateWorkerSnapshotSettingsResponse',
    ]) {
      expect(components.has(response)).toBe(true);
      expect([...reachable(components, response)]).not.toContain('UpdateWorkerSnapshotSettingsRequest');
    }
  });
});
