import { verify } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { Client } from '../../src/agent/client.js';
import { Connection, DEFAULT_BASE_URL } from '../../src/agent/connection.js';
import { AgentAPIError } from '../../src/agent/errors.js';
import { PostGripAPIError } from '../../src/internal/transport.js';
import { canonicalRequest, importSigningKeyFromBase64 } from '../../src/agent/_signing.js';
import { Agent } from '../../src/agent/agent.js';
import { activityStderr, activityStdout, Worker as IndexWorker } from '../../src/agent/index.js';
import { Worker as ModuleWorker } from '../../src/agent/worker.js';
import { defineQuery } from '../../src/agent/workflow.js';
import type { ContainerExecPayload, EnqueueTaskRequest, ShellExecPayload, Task, WorkflowExecution, WorkflowRuntimePayload } from '../../src/agent/types.js';

function workflowTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    namespace: 'default',
    queue: 'default',
    type: 'workflow:ExampleWorkflow',
    payload: {
      workflowType: 'ExampleWorkflow',
      workflowId: 'workflow-1',
      runId: 'run-1',
      args: [],
    },
    state: 'queued',
    attempt: 1,
    lease_timeout_seconds: 30,
    created_at: '2026-04-22T00:00:00Z',
    updated_at: '2026-04-22T00:00:00Z',
    ...overrides,
  } as Task;
}

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe('PostGrip Agent TypeScript Connection', () => {
  it('does not send the management token to public operations', async () => {
    let authorization: string | null = 'not-called';
    const connection = Connection.create({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      authToken: 'pgt-management',
      fetch: vi.fn<typeof fetch>(async (_input, init) => {
        authorization = new Headers(init?.headers).get('authorization');
        return new Response('{}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    });

    await connection.openapi.refreshAgentSession({ body: { refreshToken: 'pgr-runtime' } });

    expect(authorization).toBeNull();
  });

  it('loads POSTGRIP_TOKEN for a directly constructed Agent connection', async () => {
    vi.stubEnv('POSTGRIP_AGENT_URL', 'https://agent.example.test');
    vi.stubEnv('POSTGRIP_TOKEN', 'opaque-direct-token');
    try {
      let authorization: string | null = null;
      const connection = Connection.create({
        fetch: vi.fn<typeof fetch>(async (_input, init) => {
          authorization = new Headers(init?.headers).get('authorization');
          return Response.json([]);
        }),
      });
      await connection.listNamespaces();
      expect(authorization).toBe('Bearer opaque-direct-token');
    } finally {
      vi.unstubAllEnvs();
    }
  });

  // A host agent launches a workflow.runtime task with its orchestrator's URL in
  // POSTGRIP_AGENTORCHESTRATOR_URL and forbids the task from overriding POSTGRIP_*
  // variables, so a managed runtime must prefer that URL over the general ones.
  it.each<{ name: string; baseUrl?: string; env: Record<string, string>; want: string }>([
    {
      name: 'managed runtime with only the host-injected address',
      env: { POSTGRIP_AGENT_MANAGED_RUNTIME: 'true', POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test' },
      want: 'https://orchestrator.example.test',
    },
    {
      name: 'managed runtime prefers the host-injected address',
      env: {
        POSTGRIP_AGENT_MANAGED_RUNTIME: 'true',
        POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test',
        POSTGRIP_AGENT_URL: 'https://agent.example.test',
        POSTGRIP_URL: 'https://common.example.test',
      },
      want: 'https://orchestrator.example.test',
    },
    {
      name: 'explicit address wins in a managed runtime',
      baseUrl: 'https://explicit.example.test',
      env: { POSTGRIP_AGENT_MANAGED_RUNTIME: 'true', POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test' },
      want: 'https://explicit.example.test',
    },
    {
      name: 'managed runtime without a host-injected address',
      env: { POSTGRIP_AGENT_MANAGED_RUNTIME: 'true', POSTGRIP_AGENT_URL: 'https://agent.example.test' },
      want: 'https://agent.example.test',
    },
    {
      name: 'orchestrator address is ignored outside a managed runtime',
      env: {
        POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test',
        POSTGRIP_AGENT_URL: 'https://agent.example.test',
        POSTGRIP_URL: 'https://common.example.test',
      },
      want: 'https://agent.example.test',
    },
    {
      name: 'common address follows the Agent address',
      env: { POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test', POSTGRIP_URL: 'https://common.example.test' },
      want: 'https://common.example.test',
    },
    {
      name: 'built-in cloud address is the last resort',
      env: { POSTGRIP_AGENTORCHESTRATOR_URL: 'https://orchestrator.example.test' },
      want: DEFAULT_BASE_URL,
    },
  ])('resolves the Agent address: $name', ({ baseUrl, env, want }) => {
    for (const name of ['POSTGRIP_AGENT_MANAGED_RUNTIME', 'POSTGRIP_AGENTORCHESTRATOR_URL', 'POSTGRIP_AGENT_URL', 'POSTGRIP_URL']) {
      vi.stubEnv(name, env[name]);
    }
    try {
      expect(Connection.create({ baseUrl }).baseUrl).toBe(want);
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('requires manual redirect handling for JSON and archive requests', async () => {
    const redirects: Array<RequestRedirect | undefined> = [];
    const connection = Connection.create({
      baseUrl: 'https://agent.example.test',
      authToken: 'opaque-management-token',
      fetch: vi.fn<typeof fetch>(async (input, init) => {
        redirects.push(init?.redirect);
        return String(input).endsWith('/api/v1/workspaces')
          ? Response.json({ id: 'workspace-1' })
          : Response.json([]);
      }),
    });

    await connection.listNamespaces();
    await connection.uploadWorkspace(new Uint8Array([1, 2, 3]));
    expect(redirects).toEqual(['manual', 'manual']);
  });

  it('rejects an oversized response body', async () => {
    const connection = Connection.create({
      baseUrl: 'https://agent.example.test',
      fetch: vi.fn<typeof fetch>(async () => new Response('x'.repeat((40 << 20) + 1))),
    });

    await expect(connection.listNamespaces()).rejects.toThrow(/too large/);
  });

  it('follows stable workflow history pages', async () => {
    const requests: URL[] = [];
    const connection = Connection.create({
      baseUrl: 'https://agent.example.test',
      fetch: vi.fn<typeof fetch>(async (input) => {
        const url = new URL(String(input));
        requests.push(url);
        return url.searchParams.get('cursor') == null
          ? Response.json({ items: [{ id: 'event-1' }], nextCursor: 'next-page' })
          : Response.json({ items: [{ id: 'event-2' }] });
      }),
    });

    await expect(connection.getWorkflowHistory('workflow-1')).resolves.toHaveLength(2);
    expect(requests).toHaveLength(2);
    expect(requests[0]?.searchParams.get('limit')).toBe('500');
    expect(requests[1]?.searchParams.get('cursor')).toBe('next-page');
  });

  it('keeps deprecated Worker imports as Agent aliases', () => {
    expect(IndexWorker).toBe(Agent);
    expect(ModuleWorker).toBe(Agent);
  });

  it('preserves Headers instances and adds JSON content type for request bodies', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (_input, init) => (
      new Response(JSON.stringify({ id: 'task-1' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      })
    ));
    const headers = new Headers([['authorization', 'Bearer token']]);
    const connection = await Connection.connect({
      baseUrl: 'http://agent.test/',
      insecureDevelopment: true,
      headers,
      fetch: vi.fn<typeof fetch>(async (input, init) => {
        if (String(input).endsWith('/healthz')) {
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return fetchMock(input, init);
      }),
    });

    await connection.enqueueTask({ type: 'noop', payload: { ok: true } });

    const requestHeaders = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(requestHeaders.get('authorization')).toBe('Bearer token');
    expect(requestHeaders.get('content-type')).toBe('application/json');
  });

  it('preserves tuple-array headers', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input).endsWith('/healthz')) {
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      const headers = init?.headers as Headers;
      return new Response(JSON.stringify({ trace: headers.get('x-trace-id') }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      headers: [['x-trace-id', 'trace-1']],
      fetch: fetchMock,
    });

    const response = await connection.createNamespace('tenant-a');

    expect(response).toEqual({ trace: 'trace-1' });
  });

  it('uses managed agent tokens only for agent task routes', async () => {
    const seenAuth: Record<string, string | null> = {};
    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      headers: { Authorization: 'Bearer management-token' },
      agentAuth: {
        accessToken: 'agent-access-token',
        refreshToken: 'agent-refresh-token',
        accessExpiresAt: '2999-01-01T00:00:00Z',
      },
      fetch: vi.fn<typeof fetch>(async (input, init) => {
        const url = new URL(String(input));
        const headers = init?.headers as Headers;
        seenAuth[url.pathname] = headers.get('authorization');
        if (url.pathname === '/healthz') {
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (url.pathname === '/api/v1/agent/poll') {
          return new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ id: 'task-1' }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    });

    await connection.enqueueTask({ type: 'noop' });
    await connection.pollTask({ queue: 'default', agentId: 'agent-1', waitSeconds: 0 });

    expect(seenAuth['/api/v1/tasks']).toBe('Bearer agent-access-token');
    expect(seenAuth['/api/v1/agent/poll']).toBe('Bearer agent-access-token');
  });

  it('signs the final request path including a configured reverse-proxy prefix', async () => {
    const privateSeed = Buffer.alloc(32, 9).toString('base64');
    const signingKey = await importSigningKeyFromBase64(privateSeed);
    let verified = false;
    const connection = Connection.create({
      baseUrl: 'http://agent.test/postgrip-proxy',
      insecureDevelopment: true,
      agentAuth: {
        agentId: 'agent-1',
        accessToken: 'agent-access-token',
        refreshToken: 'agent-refresh-token',
        accessExpiresAt: '2999-01-01T00:00:00Z',
        signingPrivateKey: privateSeed,
      },
      fetch: vi.fn<typeof fetch>(async (input, init) => {
        const url = new URL(String(input));
        const headers = new Headers(init?.headers);
        const timestamp = Number(headers.get('x-agent-signature-timestamp'));
        const body = new TextEncoder().encode(String(init?.body ?? ''));
        const canonical = await canonicalRequest(
          init?.method ?? 'GET',
          url.pathname,
          url.search.slice(1),
          timestamp,
          body,
        );
        verified = verify(
          null,
          canonical,
          signingKey.publicKey,
          Buffer.from(headers.get('x-agent-signature') ?? '', 'base64'),
        );
        expect(url.pathname).toBe('/postgrip-proxy/api/v1/agent/tasks/task-1/complete');
        return Response.json(workflowTask({ id: 'task-1' }));
      }),
    });

    await connection.completeTask('task-1', 'agent-1', { message: 'done' });
    expect(verified).toBe(true);
  });

  it('raises typed Agent errors whose text excludes server content', async () => {
    const responses = [
      Response.json({ code: 'FORBIDDEN', message: 'standard message', requestId: 'req-1', error: 'legacy message' }, { status: 403 }),
      Response.json({ error: 'legacy message' }, { status: 400 }),
    ];
    const connection = Connection.create({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      authToken: 'management-token',
      fetch: vi.fn<typeof fetch>(async () => responses.shift()!),
    });

    const standard = await connection.listNamespaces().catch((caught: unknown) => caught);
    expect(standard).toBeInstanceOf(AgentAPIError);
    expect(standard).toBeInstanceOf(PostGripAPIError);
    expect(standard).toMatchObject({
      name: 'AgentAPIError', status: 403, code: 'FORBIDDEN', requestId: 'req-1',
      method: 'GET', route: '/api/v1/namespaces',
      message: 'postgrip-agent: "GET" "/api/v1/namespaces" -> 403 Forbidden',
    });
    expect((standard as AgentAPIError).responseBody).toContain('standard message');

    const legacy = await connection.listNamespaces().catch((caught: unknown) => caught);
    expect(legacy).toMatchObject({ status: 400, code: 'HTTP_ERROR', message: 'postgrip-agent: "GET" "/api/v1/namespaces" -> 400 Bad Request' });
    expect((legacy as Error).message).not.toContain('legacy message');
  });

  it('uses canonical agentId auth and poll options', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = new URL(String(input));
      if (url.pathname === '/healthz') {
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.pathname === '/api/v1/agent/poll') {
        expect(url.searchParams.get('agent_id')).toBe('agent-1');
        return new Response(JSON.stringify({ task: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw new Error(`unexpected request ${url.pathname}`);
    });

    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      agentAuth: {
        agentId: 'agent-1',
        accessToken: 'agent-access-token',
        refreshToken: 'agent-refresh-token',
        accessExpiresAt: '2999-01-01T00:00:00Z',
      },
      fetch: fetchMock,
    });

    await expect(connection.pollTask({ queue: 'default', agentId: 'agent-1', waitSeconds: 0 })).resolves.toBeNull();
  });

  it('maps deprecated workerId options to canonical agent poll options', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = new URL(String(input));
      if (url.pathname === '/healthz') {
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.pathname === '/api/v1/agent/poll') {
        expect(url.searchParams.get('agent_id')).toBe('agent-compat');
        return new Response(JSON.stringify({ task: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw new Error(`unexpected request ${url.pathname}`);
    });

    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      agentAuth: {
        workerId: 'agent-compat',
        accessToken: 'agent-access-token',
        refreshToken: 'agent-refresh-token',
        accessExpiresAt: '2999-01-01T00:00:00Z',
      },
      fetch: fetchMock,
    });

    await expect(connection.pollTask({ queue: 'default', workerId: 'agent-compat', waitSeconds: 0 })).resolves.toBeNull();
  });

  it('decodes a shutdown directive from a Gone poll response', async () => {
    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      agentAuth: {
        agentId: 'agent-1',
        accessToken: 'agent-access-token',
        refreshToken: 'agent-refresh-token',
        accessExpiresAt: '2999-01-01T00:00:00Z',
      },
      fetch: vi.fn<typeof fetch>(async (input) => {
        const url = new URL(String(input));
        if (url.pathname === '/healthz') {
          return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
        }
        return new Response(JSON.stringify({
          directive: { type: 'shutdown', subject: 'agent' },
        }), { status: 410 });
      }),
    });

    await expect(connection.pollTaskResponse({
      queue: 'default',
      agentId: 'agent-1',
      waitSeconds: 0,
    })).resolves.toMatchObject({ directive: { type: 'shutdown', subject: 'agent' } });
  });

  it('blocks workflow-family task submission outside managed runtimes', async () => {
    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      fetch: vi.fn<typeof fetch>(async (input) => {
        const url = new URL(String(input));
        if (url.pathname === '/healthz') {
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      }),
    });

    await expect(connection.enqueueTask({ type: 'workflow:ExampleWorkflow' }))
      .rejects.toThrow('workflow.runtime');
  });

  it('keeps workflow.runtime as the external workflow submission path', async () => {
    let seenBody: EnqueueTaskRequest | undefined;
    const connection = await Connection.connect({
      baseUrl: 'http://agent.test',
      insecureDevelopment: true,
      headers: { Authorization: 'Bearer management-token' },
      fetch: vi.fn<typeof fetch>(async (input, init) => {
        const url = new URL(String(input));
        if (url.pathname === '/healthz') {
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (url.pathname === '/api/v1/tasks') {
          seenBody = JSON.parse(String(init?.body ?? '{}')) as EnqueueTaskRequest;
          return new Response(JSON.stringify(workflowTask({
            id: 'runtime-task',
            type: 'workflow.runtime',
            payload: seenBody.payload,
          })), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        throw new Error(`unexpected request ${url.pathname}`);
      }),
    });
    const client = new Client({ connection });

    const task = await client.task.workflowRuntime({
      queue: 'default',
      command: 'sh',
      args: ['-lc', 'echo runtime'],
    });

    expect(task.id).toBe('runtime-task');
    expect(seenBody?.type).toBe('workflow.runtime');
    expect((seenBody?.payload as WorkflowRuntimePayload | undefined)?.queue).toMatch(/^postgrip-runtime-/);
    expect((seenBody?.payload as WorkflowRuntimePayload | undefined)?.queue).not.toBe('default');
  });
});

describe('PostGrip Agent TypeScript Client', () => {
  it('starts workflows with Temporal-style metadata and retry options', async () => {
    async function ExampleWorkflow(name: string): Promise<string> {
      return `hello ${name}`;
    }
    const enqueued: EnqueueTaskRequest[] = [];
    const connection = {
      enqueueTask: vi.fn(async (request: EnqueueTaskRequest) => {
        enqueued.push(request);
        return workflowTask({
          id: 'workflow-task-1',
          type: request.type,
          namespace: request.namespace,
          queue: request.queue,
          payload: { ...(request.payload as object), runId: 'run-1' },
          lease_timeout_seconds: request.lease_timeout_seconds ?? 30,
        });
      }),
    };
    const client = new Client({ connection: connection as unknown as Connection });

    const handle = await client.workflow.start(ExampleWorkflow, {
      workflowId: 'workflow-1',
      taskQueue: 'workflow-queue',
      namespace: 'tenant-a',
      args: ['PostGrip'],
      memo: { owner: 'docs' },
      ui: {
        displayName: 'Example greeting',
        description: 'Started from the SDK test',
        details: { customer: 'acme', attempt: 1 },
        tags: ['sdk', 'demo'],
      },
      searchAttributes: { customer: 'acme' },
      retry: { maximumAttempts: 3, nonRetryableErrorTypes: ['BadInput'] },
      leaseTimeoutSeconds: 12,
    });

    expect(handle.workflowId).toBe('workflow-1');
    expect(handle.runId).toBe('run-1');
    expect(enqueued[0]).toMatchObject({
      namespace: 'tenant-a',
      queue: 'workflow-queue',
      type: 'workflow:ExampleWorkflow',
      lease_timeout_seconds: 12,
    });
    expect(enqueued[0].payload).toMatchObject({
      workflowId: 'workflow-1',
      workflowType: 'ExampleWorkflow',
      args: ['PostGrip'],
      memo: {
        owner: 'docs',
        'postgrip.ui': {
          displayName: 'Example greeting',
          description: 'Started from the SDK test',
          details: { customer: 'acme', attempt: 1 },
          tags: ['sdk', 'demo'],
        },
      },
      searchAttributes: { customer: 'acme' },
      retry: { maximumAttempts: 3, nonRetryableErrorTypes: ['BadInput'] },
    });
  });

  it('targets workflow queries by run id when a handle has one', async () => {
    const answer = defineQuery<string>('answer');
    const queryTask = workflowTask({
      id: 'query-task-1',
      type: 'query:ExampleWorkflow',
      state: 'succeeded',
      result: { value: 'ready' },
    });
    const enqueued: EnqueueTaskRequest[] = [];
    const workflow: WorkflowExecution = {
      id: 'workflow-1',
      run_id: 'run-77',
      task_id: 'workflow-task-1',
      namespace: 'tenant-a',
      queue: 'workflow-queue',
      type: 'ExampleWorkflow',
      state: 'running',
      created_at: '2026-04-22T00:00:00Z',
      updated_at: '2026-04-22T00:00:00Z',
    } as WorkflowExecution;
    const connection = {
      getWorkflow: vi.fn(async (id: string) => {
        expect(id).toBe('run-77');
        return workflow;
      }),
      enqueueTask: vi.fn(async (request: EnqueueTaskRequest) => {
        enqueued.push(request);
        return { ...queryTask, payload: request.payload };
      }),
      getTask: vi.fn(async () => queryTask),
    };
    const client = new Client({ connection: connection as unknown as Connection });
    const handle = client.workflow.getHandle<string>('workflow-1', {
      runId: 'run-77',
      workflowType: 'ExampleWorkflow',
    });

    await expect(handle.query(answer)).resolves.toBe('ready');

    expect(enqueued[0]).toMatchObject({
      namespace: 'tenant-a',
      queue: 'workflow-queue',
      type: 'query:ExampleWorkflow',
    });
    expect(enqueued[0].payload).toMatchObject({
      workflowId: 'workflow-1',
      workflowRunId: 'run-77',
      queryName: 'answer',
    });
  });

  it('maps createWorkflowSchedule convenience options to server schedule requests', async () => {
    async function ScheduledWorkflow(): Promise<void> {}
    const createSchedule = vi.fn(async (request) => ({
      id: request.id ?? 'schedule-1',
      namespace: request.namespace ?? 'default',
      state: 'active',
      spec: request.spec,
      action: request.action,
      created_at: '2026-04-22T00:00:00Z',
      updated_at: '2026-04-22T00:00:00Z',
    }));
    const client = new Client({ connection: { createSchedule } as unknown as Connection });

    await client.schedule.createWorkflowSchedule({
      scheduleId: 'schedule-1',
      namespace: 'tenant-a',
      workflow: ScheduledWorkflow,
      taskQueue: 'scheduled',
      args: [],
      intervalSeconds: 60,
      timezone: 'America/Los_Angeles',
      jitterSeconds: 5,
      catchUpWindowSeconds: 300,
      missedRunPolicy: 'skip',
      workflowId: 'scheduled-workflow',
      overlapPolicy: 'skip',
      ui: {
        displayName: 'Nightly scheduled workflow',
        details: { owner: 'ops' },
      },
    });

    expect(createSchedule).toHaveBeenCalledWith(expect.objectContaining({
      id: 'schedule-1',
      namespace: 'tenant-a',
      overlap_policy: 'skip',
      spec: expect.objectContaining({
        interval_seconds: 60,
        timezone: 'America/Los_Angeles',
        jitter_seconds: 5,
        catch_up_window_seconds: 300,
        missed_run_policy: 'skip',
      }),
      action: expect.objectContaining({
        namespace: 'tenant-a',
        queue: 'scheduled',
        workflowType: 'ScheduledWorkflow',
        workflowId: 'scheduled-workflow',
        memo: {
          'postgrip.ui': {
            displayName: 'Nightly scheduled workflow',
            details: { owner: 'ops' },
          },
        },
      }),
    }));
  });
});

describe('PostGrip Agent TypeScript Agent', () => {
  it('stops polling when the server directs the agent to shut down', async () => {
    const previousManagedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      pollTaskResponse: vi.fn(async () => ({ directive: { type: 'shutdown' } })),
      configureAgentAuth: vi.fn(),
    };
    try {
      const agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: {},
        maxConcurrentTasks: 1,
      });
      await agent.run();
    } finally {
      if (previousManagedRuntime == null) {
        delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      } else {
        process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previousManagedRuntime;
      }
    }
    expect(connection.pollTaskResponse).toHaveBeenCalledOnce();
  });

  it('emits activity stdout and stderr events with task context', async () => {
    const previousManagedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      heartbeatTask: vi.fn(async () => workflowTask({ state: 'leased' })),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      completeTask: vi.fn(async () => workflowTask({ state: 'succeeded' })),
      failTask: vi.fn(async () => workflowTask({ state: 'failed' })),
    };
    let agent: Agent;
    try {
      agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: {},
        activities: {
          async processStep(name: string): Promise<string> {
            await activityStdout(`processed ${name}\n`, { stage: 'processStep', details: { name } });
            await activityStderr('diagnostic line\n');
            return 'done';
          },
        },
      });
    } finally {
      if (previousManagedRuntime == null) {
        delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      } else {
        process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previousManagedRuntime;
      }
    }

    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask(workflowTask({
      id: 'activity-task-1',
      type: 'activity:processStep',
      payload: { activityType: 'processStep', args: ['customers'] },
    }));

    expect(connection.appendTaskEvent).toHaveBeenCalledWith(
      'activity-task-1',
      expect.stringMatching(/^ts-agent-/),
      expect.objectContaining({
        kind: 'stdout',
        stream: 'stdout',
        data: 'processed customers\n',
        stage: 'processStep',
        details: { name: 'customers' },
      }),
    );
    expect(connection.appendTaskEvent).toHaveBeenCalledWith(
      'activity-task-1',
      expect.stringMatching(/^ts-agent-/),
      expect.objectContaining({
        kind: 'stderr',
        stream: 'stderr',
        data: 'diagnostic line\n',
        stage: 'activity',
      }),
    );
  });

  it('keeps activity output scoped across concurrent async activity tasks', async () => {
    const previousManagedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    const first = deferred();
    const second = deferred();
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      heartbeatTask: vi.fn(async () => workflowTask({ state: 'leased' })),
      appendTaskEvent: vi.fn(async (taskId: string, _agentId: string, event: Record<string, unknown>) => ({
        id: 'event-1',
        task_id: taskId,
        ...event,
      })),
      completeTask: vi.fn(async () => workflowTask({ state: 'succeeded' })),
      failTask: vi.fn(async () => workflowTask({ state: 'failed' })),
    };
    let agent: Agent;
    try {
      agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: {},
        activities: {
          async processStep(name: string): Promise<string> {
            await (name === 'first' ? first.promise : second.promise);
            await activityStdout(`${name}\n`);
            return name;
          },
        },
      });
    } finally {
      if (previousManagedRuntime == null) {
        delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      } else {
        process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previousManagedRuntime;
      }
    }

    const execute = (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask.bind(agent);
    const firstExecution = execute(workflowTask({
      id: 'activity-task-1',
      type: 'activity:processStep',
      payload: { activityType: 'processStep', args: ['first'] },
    }));
    const secondExecution = execute(workflowTask({
      id: 'activity-task-2',
      type: 'activity:processStep',
      payload: { activityType: 'processStep', args: ['second'] },
    }));

    await Promise.resolve();
    await Promise.resolve();
    first.resolve();
    await Promise.resolve();
    second.resolve();
    await Promise.all([firstExecution, secondExecution]);

    const stdoutCalls = connection.appendTaskEvent.mock.calls.filter((call) => call[2]?.kind === 'stdout');
    expect(stdoutCalls).toHaveLength(2);
    expect(stdoutCalls).toEqual(expect.arrayContaining([
      ['activity-task-1', expect.stringMatching(/^ts-agent-/), expect.objectContaining({ data: 'first\n' })],
      ['activity-task-2', expect.stringMatching(/^ts-agent-/), expect.objectContaining({ data: 'second\n' })],
    ]));
  });

  it('fails unsupported task types instead of completing them', async () => {
    const previousManagedRuntime = process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
    process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = 'true';
    const connection = {
      health: vi.fn(async () => ({ status: 'ok' })),
      heartbeatTask: vi.fn(async () => workflowTask({ state: 'leased' })),
      appendTaskEvent: vi.fn(async () => ({ id: 'event-1' })),
      failTask: vi.fn(async () => workflowTask({ state: 'failed' })),
    };
    let agent: Agent;
    try {
      agent = await Agent.create({
        connection: connection as unknown as Connection,
        taskQueue: 'default',
        workflows: {},
      });
    } finally {
      if (previousManagedRuntime == null) {
        delete process.env.POSTGRIP_AGENT_MANAGED_RUNTIME;
      } else {
        process.env.POSTGRIP_AGENT_MANAGED_RUNTIME = previousManagedRuntime;
      }
    }

    await (agent as unknown as { executeTask(task: Task): Promise<void> }).executeTask(workflowTask({
      id: 'unknown-task-1',
      type: 'noop',
      payload: {},
    }));

    expect(connection.failTask).toHaveBeenCalledWith(
      'unknown-task-1',
      expect.stringMatching(/^ts-agent-/),
      expect.stringContaining('unsupported TypeScript task type noop'),
      expect.objectContaining({
        failure: expect.objectContaining({
          type: 'UnsupportedTaskType',
          non_retryable: true,
        }),
      }),
    );
  });
});

describe('exec payload secret_env', () => {
  it('names secrets in secret_env on both exec payloads', () => {
    const shell: ShellExecPayload = { command: 'psql', secret_env: { PGPASSWORD: 'prod-db-password' } };
    const container: ContainerExecPayload = { image: 'postgres:17', secret_env: { PGPASSWORD: 'prod-db-password' } };
    expect(JSON.parse(JSON.stringify(shell)).secret_env).toEqual({ PGPASSWORD: 'prod-db-password' });
    expect(JSON.parse(JSON.stringify(container)).secret_env).toEqual({ PGPASSWORD: 'prod-db-password' });
  });
});
