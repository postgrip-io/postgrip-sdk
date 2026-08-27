import { Client as AgentClient } from './agent/client.js';
import { Connection } from './agent/connection.js';
import { resolvePostGripConfig, type PostGripEnvironment } from './internal/config.js';
import { ServiceClient } from './service/client.js';
import { WorkerClient } from './worker/client.js';

export interface PostGripConfig {
  readonly baseUrl?: string;
  readonly agentUrl?: string;
  readonly workerUrl?: string;
  readonly serviceUrl?: string;
  readonly token?: string;
  readonly fetch?: typeof globalThis.fetch;
  readonly insecureDevelopment?: boolean;
  readonly enableRetries?: boolean;
  readonly environment?: PostGripEnvironment;
}

/** A unified client for the Agent, Worker, and Service APIs. */
export class PostGrip {
  readonly agent: AgentClient;
  readonly workers: WorkerClient;
  readonly services: ServiceClient;

  constructor(config: PostGripConfig) {
    const resolved = resolvePostGripConfig(config);
    const connection = Connection.create({
      baseUrl: resolved.agentUrl,
      authToken: resolved.token,
      fetch: config.fetch,
      insecureDevelopment: config.insecureDevelopment,
    });
    this.agent = new AgentClient({ connection });
    this.workers = new WorkerClient({
      baseUrl: resolved.workerUrl,
      token: resolved.token,
      fetch: config.fetch,
      insecureDevelopment: config.insecureDevelopment,
      enableRetries: config.enableRetries,
    });
    this.services = new ServiceClient({
      baseUrl: resolved.serviceUrl,
      token: resolved.token,
      fetch: config.fetch,
      insecureDevelopment: config.insecureDevelopment,
      enableRetries: config.enableRetries,
    });
  }

  static fromEnv(config: PostGripConfig = {}): PostGrip {
    return new PostGrip(config);
  }
}
