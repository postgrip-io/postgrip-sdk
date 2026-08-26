import { describe, expect, it, vi } from 'vitest';

import { PostGrip } from '../src/index.js';

describe('PostGrip', () => {
  it('uses one token for Agent, Worker, and Service requests', async () => {
    const authorizations: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      authorizations.push(new Headers(init?.headers).get('authorization') ?? '');
      const path = new URL(String(input)).pathname;
      if (path.endsWith('/ready')) return Response.json({ status: 'ready', stats: {} });
      if (path.endsWith('/workflows')) return Response.json([]);
      return Response.json({ items: [] });
    }) as typeof globalThis.fetch;

    const client = new PostGrip({
      baseUrl: 'https://api.example.test',
      token: 'pgt_one-token',
      fetch: fetchImpl,
    });

    await client.agent.workflow.list();
    await client.workers.list();
    await client.services.list();
    expect(authorizations).toEqual([
      'Bearer pgt_one-token',
      'Bearer pgt_one-token',
      'Bearer pgt_one-token',
    ]);
  });

  it('applies explicit, plane, then common URL precedence from the environment', async () => {
    const urls: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      if (new URL(String(input)).pathname.endsWith('/workflows')) return Response.json([]);
      return Response.json({ items: [] });
    }) as typeof globalThis.fetch;
    const client = PostGrip.fromEnv({
      agentUrl: 'https://explicit-agent.example.test',
      environment: {
        POSTGRIP_URL: 'https://common.example.test',
        POSTGRIP_AGENT_URL: 'https://ignored-agent.example.test',
        POSTGRIP_WORKER_URL: 'https://worker.example.test',
        POSTGRIP_TOKEN: 'pgt_environment',
      },
      fetch: fetchImpl,
    });

    await client.agent.workflow.list();
    await client.workers.list();
    await client.services.list();
    expect(urls[0]).toContain('explicit-agent.example.test');
    expect(urls[1]).toContain('worker.example.test');
    expect(urls[2]).toContain('common.example.test');
  });
});
