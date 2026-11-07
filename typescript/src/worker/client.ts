import {
  OpenAPIClient,
  resolveOpenAPIOperation,
  type OpenAPIAssignmentList,
  type OpenAPICheckWorkerResponse,
  type OpenAPICreateWorkerRequest,
  type OpenAPICreateWorkerResponse,
  type OpenAPICreateWorkerSnapshotResponse,
  type OpenAPIHealthResponse,
  type OpenAPIJob,
  type OpenAPIJobList,
  type OpenAPIJobState,
  type OpenAPIOperationalLogEntry,
  type OpenAPIOperationalLogList,
  type OpenAPISecurityLogEntry,
  type OpenAPISecurityLogList,
  type OpenAPIStorageDestinationList,
  type OpenAPIUpdateWorkerSnapshotSettingsRequest,
  type OpenAPIUpdateWorkerSnapshotSettingsResponse,
  type OpenAPIUpgradeWorkerResponse,
  type OpenAPIWorker,
  type OpenAPIWorkerList,
  type OpenAPIWorkerOperationResponse,
  type OpenAPIWorkerSnapshotList,
  type OpenAPIWorkerSnapshotSettings,
  type OpenAPIWorkerSnapshotStatus,
  type OpenAPIOperationId,
  type OpenAPIResponseBody,
} from './generated/openapi.js';
import { validateBaseUrl, validateManagementToken, type PostGripEnvironment } from '../internal/config.js';
import { followPages } from '../internal/polling.js';
import { configuredTimeoutMs, Executor, PostGripAPIError, validateIdempotencyKey } from '../internal/transport.js';

const RETRY_MAX_ATTEMPTS = 3;
const RETRY_MAX_DELAY_MS = 2_000;
const RETRY_AFTER_MAX_DELAY_MS = 30_000;

/**
 * Lifetime of createWorkerSnapshot. The server waits up to 5 minutes for the
 * run before it answers, so the call needs longer than the default exchange.
 */
const SNAPSHOT_RUN_LIFETIME_MS = 6 * 60_000;

/**
 * Per-operation exchange policy. createWorkerSnapshot's 502 and 504 answers are
 * not kept against the Idempotency-Key, so an automatic resend, even with the
 * same key, would take another snapshot; the caller reads the status first.
 */
const OPERATION_CALL_POLICY: Readonly<Partial<Record<OpenAPIOperationId, {
  readonly lifetimeMs: number;
  readonly noRetryStatuses: readonly number[];
}>>> = {
  createWorkerSnapshot: { lifetimeMs: SNAPSHOT_RUN_LIFETIME_MS, noRetryStatuses: [502, 504] },
};

export interface WorkerClientConfig {
  readonly baseUrl: string;
  readonly token: string;
  readonly fetch?: typeof globalThis.fetch;
  readonly insecureDevelopment?: boolean;
  readonly enableRetries?: boolean;
  readonly followIntervalMs?: number;
  /** Bound on each HTTP exchange in milliseconds, from 1 to 2147483647; defaults to 30000. An earlier `signal` abort still wins. */
  readonly timeoutMs?: number;
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

export class WorkerAPIError extends PostGripAPIError {
  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string,
    details?: Readonly<Record<string, unknown>>,
    retryAfterMs?: number,
  ) {
    super(status, code, message, requestId, details, retryAfterMs);
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

  private readonly executor: Executor;
  private readonly followIntervalMs: number;

  constructor(config: WorkerClientConfig) {
    this.executor = new Executor({
      plane: 'Worker',
      baseUrl: validateBaseUrl('Worker', config.baseUrl, config.insecureDevelopment),
      fetch: config.fetch ?? globalThis.fetch,
      managementToken: validateManagementToken(config.token),
      retry: {
        enabled: config.enableRetries ?? false,
        maxAttempts: RETRY_MAX_ATTEMPTS,
        maxDelayMs: RETRY_MAX_DELAY_MS,
        retryAfterMaxDelayMs: RETRY_AFTER_MAX_DELAY_MS,
      },
      timeoutMs: configuredTimeoutMs('Worker', config.timeoutMs),
      createError: ({ status, code, message, requestId, details, retryAfterMs }) =>
        new WorkerAPIError(status, code, message, requestId, details, retryAfterMs),
    });
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

  /** Read the Worker's snapshot schedule and last run; answered with `enabled: false` when snapshots are off. */
  snapshotStatus(workerId: string, options: RequestOptions = {}): Promise<OpenAPIWorkerSnapshotStatus> {
    return this.request('getWorkerSnapshotStatus', { path: { workerId }, signal: options.signal });
  }

  /** List the Worker's archives in its storage destination, newest first. The list is not paged. */
  snapshots(workerId: string, options: RequestOptions = {}): Promise<OpenAPIWorkerSnapshotList> {
    return this.request('listWorkerSnapshots', { path: { workerId }, signal: options.signal });
  }

  /**
   * Run a snapshot on the Worker and wait for it. The server waits up to 5
   * minutes, so the exchange is allowed 6 minutes, and its 502 and 504 answers
   * are never retried automatically: a `504` `SNAPSHOT_UNCONFIRMED` run may
   * still land, so read `snapshotStatus` before resending with a new key.
   */
  takeSnapshot(workerId: string, options: MutationOptions): Promise<OpenAPICreateWorkerSnapshotResponse> {
    return this.mutate('createWorkerSnapshot', workerId, options);
  }

  /** Read the Worker's snapshot settings. The signing key is never answered; `hasSigningKey` reports one. */
  snapshotSettings(workerId: string, options: RequestOptions = {}): Promise<OpenAPIWorkerSnapshotSettings> {
    return this.request('getWorkerSnapshotSettings', { path: { workerId }, signal: options.signal });
  }

  /**
   * Replace the Worker's whole snapshot settings record: every field but
   * `enabled` takes its zero value when omitted. `signingKey` is write-only;
   * omit it to keep the stored key.
   */
  updateSnapshotSettings(
    workerId: string,
    input: OpenAPIUpdateWorkerSnapshotSettingsRequest,
    options: MutationOptions,
  ): Promise<OpenAPIUpdateWorkerSnapshotSettingsResponse> {
    validateIdempotencyKey(options.idempotencyKey);
    return this.request('updateWorkerSnapshotSettings', {
      body: input,
      path: { workerId },
      signal: options.signal,
      idempotencyKey: options.idempotencyKey,
    });
  }

  /**
   * List the organization's storage destinations, ordered by name; the list is
   * not paged. A destination's `id` is the `storageDestinationId` that
   * `updateSnapshotSettings` takes. No credential is answered: the access key
   * and secret stay on the Workers.
   */
  storageDestinations(options: RequestOptions = {}): Promise<OpenAPIStorageDestinationList> {
    return this.request('listStorageDestinations', { signal: options.signal });
  }

  private mutate<I extends 'checkWorker' | 'placeWorkerInMaintenance' | 'resumeWorkerFromMaintenance' | 'upgradeWorker' | 'createWorkerSnapshot'>(
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

  private request<I extends OpenAPIOperationId>(operationId: I, options: InternalRequestOptions): Promise<OpenAPIResponseBody<I>> {
    const operation = resolveOpenAPIOperation(operationId, options.path, encodeQuery(options.query));
    const policy = OPERATION_CALL_POLICY[operationId];
    return this.executor.request<OpenAPIResponseBody<I>>({
      operation,
      body: options.body,
      idempotencyKey: options.idempotencyKey,
      signal: options.signal,
      lifetimeMs: policy?.lifetimeMs,
      noRetryStatuses: policy?.noRetryStatuses,
    });
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
