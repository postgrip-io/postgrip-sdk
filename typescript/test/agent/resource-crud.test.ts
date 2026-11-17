import { describe, expect, it, vi } from 'vitest';
import { Connection } from '../../src/agent/connection.js';

describe('resource CRUD public boundary', () => {
  it('keeps enrollment credentials separate and preserves explicit empty labels', async () => {
    const requests: { url: string; method: string; authorization: string | null; body: unknown }[] = [];
    const connection = Connection.create({ baseUrl: 'http://agent.test', insecureDevelopment: true, authToken: 'pgt-management',
      fetch: vi.fn<typeof fetch>(async (url, init) => {
        requests.push({ url: String(url), method: init!.method!, authorization: new Headers(init?.headers).get('authorization'), body: JSON.parse(String(init?.body)) });
        return Response.json({ id: 's/1', name: 'renamed' });
      }),
    });
    await connection.openapi.enrollAgent({ body: { enrollmentKey: 'one-time', agentId: 'host', signaturePublicKey: 'public-key' } });
    await connection.openapi.updateSandbox({ pathParameters: { sandboxId: 's/1' }, body: { name: 'renamed' } });
    await connection.openapi.updateSandbox({ pathParameters: { sandboxId: 's/1' }, body: { labels: {} } });
    expect(requests).toEqual([
      { url: 'http://agent.test/api/v1/agent/enroll', method: 'POST', authorization: null, body: { enrollmentKey: 'one-time', agentId: 'host', signaturePublicKey: 'public-key' } },
      { url: 'http://agent.test/api/v1/sandboxes/s%2F1', method: 'PATCH', authorization: 'Bearer pgt-management', body: { name: 'renamed' } },
      { url: 'http://agent.test/api/v1/sandboxes/s%2F1', method: 'PATCH', authorization: 'Bearer pgt-management', body: { labels: {} } },
    ]);
  });
});
