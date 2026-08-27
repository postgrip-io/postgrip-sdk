import {
  OpenAPIClient,
  resolveOpenAPIOperation,
  type OpenAPIAssignmentList,
  type OpenAPICheckWorkerResponse,
  type OpenAPICreateWorkerRequest,
  type OpenAPICreateWorkerResponse,
  type OpenAPIHealthResponse,
  type OpenAPIJob,
  type OpenAPIJobList,
  type OpenAPIJobState,
  type OpenAPIOperationalLogEntry,
  type OpenAPIOperationalLogList,
  type OpenAPISecurityLogEntry,
  type OpenAPISecurityLogList,
  type OpenAPIUpgradeWorkerResponse,
  type OpenAPIWorker,
  type OpenAPIWorkerList,
  type OpenAPIWorkerOperationResponse,
  type OpenAPIOperationId,
  type OpenAPIResponseBody,
} from './generated/openapi.js';
import { validateBaseUrl, validateManagementToken, type PostGripEnvironment } from '../internal/config.js';
import { readBoundedResponseBody } from '../internal/http.js';
import { abortableDelay, followPages } from '../internal/polling.js';

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);

export interface WorkerClientConfig {
  readonly baseUrl: string;
  readonly token: string;
  readonly fetch?: typeof globalThis.fetch;
  readonly insecureDevelopment?: boolean;
  readonly enableRetries?: boolean;
  readonly followIntervalMs?: number;
}

export interface WorkerClientEnvironmentConfig extends Omit<WorkerClientConfig, 'baseUrl' | 'token'> {
  readonly environment?: PostGripEnvironment;
}

export interface RequestOptions {
  readonly signal?: AbortSignal;
}

export interface ListWorkersOptions extends RequestOptions {
  readonly pageSize?: number;
  readonly pageToken?: string;
  readonly status?: string;
  readonly trustState?: string;
}

export interface ListJobsOptions extends RequestOptions {
  readonly pageSize?: number;
  readonly pageToken?: string;
  readonly state?: OpenAPIJobState;
}

export interface OperationalLogOptions extends RequestOptions {
  readonly cursor?: string;
  readonly limit?: number;
  readonly window?: string;
  readonly since?: string;
  readonly service?: string;
  readonly stream?: 'stdout' | 'stderr';
}

export interface SecurityLogOptions extends RequestOptions {
  readonly cursor?: string;
  readonly limit?: number;
  readonly window?: string;
  readonly since?: string;
  readonly severity?: 'debug' | 'info' | 'warn' | 'error';
  readonly correlationId?: string;
  readonly focus?: string;
}

export interface MutationOptions extends RequestOptions {
  readonly idempotencyKey: string;
}

export class WorkerAPIError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly details?: Readonly<Record<string, unknown>>,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = 'WorkerAPIError';
  }
}

interface InternalRequestOptions {
  readonly body?: unknown;
  readonly path?: Readonly<Record<string, string>>;
  readonly query?: object | URLSearchParams;
  readonly signal?: AbortSignal;
  readonly idempotencyKey?: string;
}

export class WorkerClient {
  readonly openapi: OpenAPIClient;
  readonly operationalLogs = {
    list: (workerId: string, options: OperationalLogOptions = {}) =>
      this.listOperationalLogs(workerId, options),
    follow: (workerId: string, options: OperationalLogOptions = {}) =>
      this.followOperationalLogs(workerId, options),
  };

  readonly securityLogs = {
    list: (workerId: string, options: SecurityLogOptions = {}) =>
      this.listSecurityLogs(workerId, options),
    follow: (workerId: string, options: SecurityLogOptions = {}) =>
      this.followSecurityLogs(workerId, options),
  };

  private readonly baseUrl: URL;
  private readonly token: string;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly retriesEnabled: boolean;
  private readonly followIntervalMs: number;

  constructor(config: WorkerClientConfig) {
    this.baseUrl = validateBaseUrl('Worker', config.baseUrl, config.insecureDevelopment);
    this.token = validateManagementToken(config.token);
    this.fetchImpl = config.fetch ?? globalThis.fetch;
    this.retriesEnabled = config.enableRetries ?? false;
    this.followIntervalMs = Math.max(1, config.followIntervalMs ?? 2_000);
    this.openapi = new OpenAPIClient((id, options) => {
      const headers = options.headers as Readonly<Record<string, string>> | undefined;
      return this.request(id, {
        body: options.body,
        path: options.pathParameters as Readonly<Record<string, string>> | undefined,
        query: options.query,
        signal: options.signal,
        idempotencyKey: headers?.['Idempotency-Key'],
      });
    });
  }

  static fromEnv(config: WorkerClientEnvironmentConfig = {}): WorkerClient {
    const { environment = process.env, ...overrides } = config;
    return new WorkerClient({
      ...overrides,
      baseUrl: environment.POSTGRIP_WORKER_URL ?? environment.POSTGRIP_URL ?? '',
      token: environment.POSTGRIP_TOKEN ?? '',
    });
  }

  health(options: RequestOptions = {}): Promise<OpenAPIHealthResponse> {
    return this.request('workerOrchestratorHealth', { signal: options.signal });
  }

  async list(options: ListWorkersOptions = {}): Promise<OpenAPIWorkerList> {
    return this.request('listWorkers', { query: options, signal: options.signal });
  }

  async *pages(options: ListWorkersOptions = {}): AsyncGenerator<OpenAPIWorkerList> {
    let pageToken = options.pageToken;
    do {
      const page = await this.list({ ...options, pageToken });
      yield page;
      pageToken = page.nextPageToken;
    } while (pageToken);
  }

  get(workerId: string, options: RequestOptions = {}): Promise<OpenAPIWorker> {
    return this.request('getWorker', { path: { workerId }, signal: options.signal });
  }

  /**
   * Register a pending Worker with caller-owned, write-only bootstrap values.
   * Persist the input and idempotency key before calling this method so a lost
   * response can be replayed without creating a second Worker.
   */
  create(
    input: OpenAPICreateWorkerRequest,
    options: MutationOptions,
  ): Promise<OpenAPICreateWorkerResponse> {
    validateIdempotencyKey(options.idempotencyKey);
    return this.request('createWorker', {
      body: input,
      signal: options.signal,
      idempotencyKey: options.idempotencyKey,
    });
  }

  assignments(workerId: string, options: RequestOptions = {}): Promise<OpenAPIAssignmentList> {
    return this.request('listWorkerAssignments', { path: { workerId }, signal: options.signal });
  }

  jobs(workerId: string, options: ListJobsOptions = {}): Promise<OpenAPIJobList> {
    return this.request('listWorkerJobs', { path: { workerId }, query: options, signal: options.signal });
  }

  async *jobPages(workerId: string, options: ListJobsOptions = {}): AsyncGenerator<OpenAPIJobList> {
    let pageToken = options.pageToken;
    do {
      const page = await this.jobs(workerId, { ...options, pageToken });
      yield page;
      pageToken = page.nextPageToken;
    } while (pageToken);
  }

  job(workerId: string, jobId: string, options: RequestOptions = {}): Promise<OpenAPIJob> {
    return this.request('getWorkerJob', { path: { workerId, jobId }, signal: options.signal });
  }

  check(workerId: string, options: MutationOptions): Promise<OpenAPICheckWorkerResponse> {
    return this.mutate('checkWorker', workerId, options);
  }

  maintenance(workerId: string, options: MutationOptions): Promise<OpenAPIWorkerOperationResponse> {
    return this.mutate('placeWorkerInMaintenance', workerId, options);
  }

  resume(workerId: string, options: MutationOptions): Promise<OpenAPIWorkerOperationResponse> {
    return this.mutate('resumeWorkerFromMaintenance', workerId, options);
  }

  upgrade(workerId: string, options: MutationOptions): Promise<OpenAPIUpgradeWorkerResponse> {
    return this.mutate('upgradeWorker', workerId, options);
  }

  private mutate<I extends 'checkWorker' | 'placeWorkerInMaintenance' | 'resumeWorkerFromMaintenance' | 'upgradeWorker'>(
    operation: I,
    workerId: string,
    options: MutationOptions,
  ): Promise<OpenAPIResponseBody<I>> {
    validateIdempotencyKey(options.idempotencyKey);
    return this.request(operation, {
      path: { workerId },
      signal: options.signal,
      idempotencyKey: options.idempotencyKey,
    });
  }

  private listOperationalLogs(workerId: string, options: OperationalLogOptions): Promise<OpenAPIOperationalLogList> {
    return this.request('listWorkerOperationalLogs', { path: { workerId }, query: options, signal: options.signal });
  }

  private listSecurityLogs(workerId: string, options: SecurityLogOptions): Promise<OpenAPISecurityLogList> {
    return this.request('listWorkerSecurityLogs', { path: { workerId }, query: options, signal: options.signal });
  }

  private async *followOperationalLogs(workerId: string, options: OperationalLogOptions): AsyncGenerator<OpenAPIOperationalLogEntry> {
    yield* followPages(
      (cursor) => this.listOperationalLogs(workerId, { ...options, cursor }),
      {
        cursor: options.cursor,
        signal: options.signal,
        emptyPageDelayMs: () => this.followIntervalMs,
        entryId: (entry) => entry.id,
      },
    );
  }

  private async *followSecurityLogs(workerId: string, options: SecurityLogOptions): AsyncGenerator<OpenAPISecurityLogEntry> {
    yield* followPages(
      (cursor) => this.listSecurityLogs(workerId, { ...options, cursor }),
      {
        cursor: options.cursor,
        signal: options.signal,
        emptyPageDelayMs: () => this.followIntervalMs,
        entryId: (entry) => entry.id,
      },
    );
  }

  private async request<I extends OpenAPIOperationId>(operationId: I, options: InternalRequestOptions): Promise<OpenAPIResponseBody<I>> {
    const query = encodeQuery(options.query);
    const operation = resolveOpenAPIOperation(operationId, options.path, query);
    const endpoint = new URL(`${this.baseUrl.href.replace(/\/+$/, '')}${operation.path}`);
    const maxAttempts = this.retriesEnabled && (operation.method === 'GET' || options.idempotencyKey) ? 3 : 1;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      options.signal?.throwIfAborted();
      let response: Response;
      try {
        const encodedBody = options.body === undefined ? undefined : JSON.stringify(options.body);
        response = await this.fetchImpl(endpoint, {
          method: operation.method,
          headers: {
            Accept: 'application/json',
            ...(encodedBody === undefined ? {} : { 'Content-Type': 'application/json' }),
            ...(operation.authLane === 'worker-management' ? { Authorization: `Bearer ${this.token}` } : {}),
            ...(options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : {}),
          },
          body: encodedBody,
          redirect: 'manual',
          signal: options.signal,
        });
      } catch (error) {
        if (attempt < maxAttempts && !options.signal?.aborted) {
          await abortableDelay(jitter(attempt), options.signal);
          continue;
        }
        throw error;
      }
      if (response.ok) {
        return JSON.parse(await readBoundedResponseBody(response, 'Worker')) as OpenAPIResponseBody<I>;
      }
      const apiError = await decodeError(response);
      if (attempt < maxAttempts && RETRYABLE_STATUS.has(response.status)) {
        const retryAfterMs = response.status === 429 || response.status === 503
          ? apiError.retryAfterMs
          : undefined;
        await abortableDelay(retryAfterMs ?? jitter(attempt), options.signal);
        continue;
      }
      throw apiError;
    }
    throw new Error('PostGrip Worker request attempts exhausted');
  }
}

function encodeQuery(query?: object | URLSearchParams): URLSearchParams | undefined {
  if (!query) return undefined;
  if (query instanceof URLSearchParams) return query;
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (key === 'signal' || value == null) continue;
    result.set(key, String(value));
  }
  return result;
}

function validateIdempotencyKey(key: string): void {
  if (!/^[!-~]{1,128}$/.test(key)) {
    throw new Error('idempotencyKey must contain 1 to 128 visible ASCII characters');
  }
}

async function decodeError(response: Response): Promise<WorkerAPIError> {
  let value: Record<string, unknown> = {};
  try {
    const decoded: unknown = JSON.parse(await readBoundedResponseBody(response, 'Worker'));
    if (typeof decoded === 'object' && decoded !== null && !Array.isArray(decoded)) {
      value = decoded as Record<string, unknown>;
    }
  } catch {
    // The typed fallback intentionally excludes the upstream response body.
  }
  return new WorkerAPIError(
    response.status,
    typeof value.code === 'string' ? value.code : 'HTTP_ERROR',
    typeof value.message === 'string' ? value.message : response.statusText,
    typeof value.requestId === 'string' ? value.requestId : response.headers.get('x-request-id') ?? '',
    typeof value.details === 'object' && value.details !== null ? value.details as Record<string, unknown> : undefined,
    parseRetryAfter(response.headers.get('retry-after')),
  );
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds * 1_000, 30_000);
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return undefined;
  return Math.min(Math.max(timestamp - Date.now(), 0), 30_000);
}

function jitter(attempt: number): number {
  return Math.random() * Math.min(200 * 2 ** (attempt - 1), 2_000);
}
