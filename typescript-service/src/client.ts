import {
  resolveOpenAPIOperation,
  type OpenAPICheckServiceRequest,
  type OpenAPIDeployment,
  type OpenAPIDeploymentList,
  type OpenAPIDeploymentOperationResponse,
  type OpenAPIDeployPreview,
  type OpenAPIDeployServiceRequest,
  type OpenAPIEnvironment,
  type OpenAPIEnvironmentList,
  type OpenAPILogEntry,
  type OpenAPILogList,
  type OpenAPIOperationId,
  type OpenAPIRedeployServiceRequest,
  type OpenAPIResponseBody,
  type OpenAPIService,
  type OpenAPIServiceKind,
  type OpenAPIServiceList,
  type OpenAPIServiceMode,
  type OpenAPIServiceOperationResponse,
  type OpenAPIServiceSource,
  type OpenAPIServiceStatus,
  type OpenAPIServiceStatusValue,
} from './generated/openapi.js';

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);
const MAX_RESPONSE_BYTES = 4 << 20;
const DEFAULT_RETRY_MAX_ATTEMPTS = 3;
const MAXIMUM_RETRY_MAX_ATTEMPTS = 3;
const DEFAULT_RETRY_MAX_DELAY_MS = 2_000;
const MAXIMUM_RETRY_MAX_DELAY_MS = 2_000;
const DEFAULT_RETRY_AFTER_MAX_DELAY_MS = 30_000;
const MAXIMUM_RETRY_AFTER_MAX_DELAY_MS = 30_000;

export interface ServiceRetryConfig {
  readonly maxAttempts?: number;
  readonly maxDelayMs?: number;
  readonly retryAfterMaxDelayMs?: number;
}

export interface ServiceClientConfig {
  readonly baseUrl: string;
  readonly token: string;
  readonly fetch?: typeof globalThis.fetch;
  readonly insecureDevelopment?: boolean;
  readonly enableRetries?: boolean;
  readonly retry?: ServiceRetryConfig;
  readonly followIntervalMs?: number;
}

export interface ServiceClientEnvironmentConfig extends Omit<ServiceClientConfig, 'baseUrl' | 'token'> {
  readonly environment?: Readonly<Record<string, string | undefined>>;
}

export interface RequestOptions {
  readonly signal?: AbortSignal;
}

export interface ServiceReference {
  readonly source: OpenAPIServiceSource;
  readonly id: string;
}

export interface ListServicesOptions extends RequestOptions {
  readonly kind?: OpenAPIServiceKind;
  readonly mode?: OpenAPIServiceMode;
  readonly status?: OpenAPIServiceStatusValue;
  readonly workerId?: string;
  readonly limit?: number;
  readonly cursor?: string;
}

export interface ServiceStatusOptions extends RequestOptions {
  readonly environment?: string;
}

export interface ListEnvironmentsOptions extends RequestOptions {
  readonly limit?: number;
  readonly cursor?: string;
}

export interface ListDeploymentsOptions extends RequestOptions {
  readonly environment?: string;
  readonly status?: string;
  readonly limit?: number;
  readonly cursor?: string;
}

export interface ServiceLogOptions extends RequestOptions {
  readonly kind?: 'build' | 'runtime';
  readonly environmentId?: string;
  readonly deploymentId?: string;
  readonly limit?: number;
  readonly cursor?: string;
  readonly follow?: boolean;
}

export interface MutationOptions extends RequestOptions {
  readonly idempotencyKey: string;
}

export interface CheckServiceOptions extends MutationOptions {
  readonly environmentId?: string;
}

export interface PreviewDeployOptions extends RequestOptions {
  readonly environment?: string;
  readonly branch?: string;
}

export interface DeployOptions extends MutationOptions, OpenAPIDeployServiceRequest {}
export interface RedeployOptions extends MutationOptions, OpenAPIRedeployServiceRequest {}

export interface RuntimeOperationOptions extends MutationOptions {
  readonly expectedDeploymentId: string;
}

export class ServiceAPIError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly details?: Readonly<Record<string, unknown>>,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = 'ServiceAPIError';
  }
}

interface InternalRequestOptions {
  readonly path?: Readonly<Record<string, string>>;
  readonly query?: Readonly<Record<string, unknown>>;
  readonly body?: unknown;
  readonly signal?: AbortSignal;
  readonly idempotencyKey?: string;
}

interface RetryPolicy {
  readonly maxAttempts: number;
  readonly maxDelayMs: number;
  readonly retryAfterMaxDelayMs: number;
}

export class ServiceClient {
  readonly logs = {
    list: (service: ServiceReference, options: ServiceLogOptions = {}) => this.listLogs(service, options),
    follow: (service: ServiceReference, options: ServiceLogOptions = {}) => this.followLogs(service, options),
  };

  private readonly baseUrl: URL;
  private readonly token: string;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly retriesEnabled: boolean;
  private readonly retryPolicy: RetryPolicy;
  private readonly followIntervalMs: number;

  constructor(config: ServiceClientConfig) {
    const rawBaseUrl = config.baseUrl.trim();
    const baseUrl = new URL(rawBaseUrl);
    if (baseUrl.protocol !== 'https:' && !(config.insecureDevelopment && baseUrl.protocol === 'http:')) {
      throw new Error('PostGrip Service baseUrl must use HTTPS unless insecureDevelopment is enabled');
    }
    if (/[?#]/.test(rawBaseUrl) || baseUrl.search || baseUrl.hash) {
      throw new Error('PostGrip Service baseUrl must not contain a query or fragment');
    }
    if (!config.token.trim().startsWith('pgwm_')) {
      throw new Error('PostGrip Service token must use the pgwm_ management prefix');
    }
    this.baseUrl = baseUrl;
    this.token = config.token.trim();
    this.fetchImpl = config.fetch ?? globalThis.fetch;
    this.retriesEnabled = config.enableRetries ?? false;
    this.retryPolicy = configuredRetryPolicy(config.retry);
    this.followIntervalMs = Math.max(1, config.followIntervalMs ?? 2_000);
  }

  static fromEnv(config: ServiceClientEnvironmentConfig = {}): ServiceClient {
    const { environment = processEnvironment(), ...overrides } = config;
    return new ServiceClient({
      ...overrides,
      baseUrl: environment.POSTGRIP_WORKERORCHESTRATOR_URL ?? '',
      token: environment.POSTGRIP_SERVICE_API_TOKEN ?? '',
    });
  }

  list(options: ListServicesOptions = {}): Promise<OpenAPIServiceList> {
    return this.request('listServices', {
      query: {
        kind: options.kind,
        mode: options.mode,
        status: options.status,
        worker: options.workerId,
        limit: options.limit,
        cursor: options.cursor,
      },
      signal: options.signal,
    });
  }

  async *pages(options: ListServicesOptions = {}): AsyncGenerator<OpenAPIServiceList> {
    let cursor = options.cursor;
    do {
      const page = await this.list({ ...options, cursor });
      yield page;
      cursor = page.nextCursor || undefined;
    } while (cursor);
  }

  resolve(value: string, options: RequestOptions = {}): Promise<OpenAPIService> {
    return this.request('resolveService', { query: { value }, signal: options.signal });
  }

  get(service: ServiceReference, options: RequestOptions = {}): Promise<OpenAPIService> {
    return this.request('getService', { path: servicePath(service), signal: options.signal });
  }

  status(service: ServiceReference, options: ServiceStatusOptions = {}): Promise<OpenAPIServiceStatus> {
    return this.request('getServiceStatus', {
      path: servicePath(service),
      query: { environment: options.environment },
      signal: options.signal,
    });
  }

  environments(service: ServiceReference, options: ListEnvironmentsOptions = {}): Promise<OpenAPIEnvironmentList> {
    return this.request('listServiceEnvironments', {
      path: servicePath(service),
      query: { limit: options.limit, cursor: options.cursor },
      signal: options.signal,
    });
  }

  async *environmentPages(service: ServiceReference, options: ListEnvironmentsOptions = {}): AsyncGenerator<OpenAPIEnvironmentList> {
    let cursor = options.cursor;
    do {
      const page = await this.environments(service, { ...options, cursor });
      yield page;
      cursor = page.nextCursor || undefined;
    } while (cursor);
  }

  environment(projectId: string, value: string, options: RequestOptions = {}): Promise<OpenAPIEnvironment> {
    return this.request('resolveServiceEnvironment', {
      path: { serviceId: projectId }, query: { value }, signal: options.signal,
    });
  }

  deployments(service: ServiceReference, options: ListDeploymentsOptions = {}): Promise<OpenAPIDeploymentList> {
    return this.request('listServiceDeployments', {
      path: servicePath(service),
      query: { environment: options.environment, status: options.status, limit: options.limit, cursor: options.cursor },
      signal: options.signal,
    });
  }

  async *deploymentPages(service: ServiceReference, options: ListDeploymentsOptions = {}): AsyncGenerator<OpenAPIDeploymentList> {
    let cursor = options.cursor;
    do {
      const page = await this.deployments(service, { ...options, cursor });
      yield page;
      cursor = page.nextCursor || undefined;
    } while (cursor);
  }

  deployment(projectId: string, deploymentId: string, options: RequestOptions = {}): Promise<OpenAPIDeployment> {
    return this.request('getServiceDeployment', {
      path: { serviceId: projectId, deploymentId }, signal: options.signal,
    });
  }

  check(service: ServiceReference, options: CheckServiceOptions): Promise<OpenAPIServiceOperationResponse> {
    const body: OpenAPICheckServiceRequest = {};
    if (options.environmentId) body.environmentId = options.environmentId;
    return this.mutate('checkService', {
      path: servicePath(service), body, ...mutationRequest(options),
    });
  }

  previewDeploy(projectId: string, options: PreviewDeployOptions = {}): Promise<OpenAPIDeployPreview> {
    return this.request('previewServiceDeploy', {
      path: { serviceId: projectId },
      query: { environment: options.environment, branch: options.branch },
      signal: options.signal,
    });
  }

  deploy(projectId: string, options: DeployOptions): Promise<OpenAPIDeploymentOperationResponse> {
    const { environmentId, branch, expectedCommitSha } = options;
    return this.mutate('deployService', {
      path: { serviceId: projectId }, body: { environmentId, branch, expectedCommitSha }, ...mutationRequest(options),
    });
  }

  redeploy(projectId: string, options: RedeployOptions): Promise<OpenAPIDeploymentOperationResponse> {
    const { environmentId, deploymentId } = options;
    return this.mutate('redeployService', {
      path: { serviceId: projectId }, body: { environmentId, deploymentId }, ...mutationRequest(options),
    });
  }

  cancel(projectId: string, deploymentId: string, options: MutationOptions): Promise<OpenAPIDeploymentOperationResponse> {
    return this.mutate('cancelServiceDeployment', {
      path: { serviceId: projectId, deploymentId }, ...mutationRequest(options),
    });
  }

  rollback(projectId: string, deploymentId: string, options: MutationOptions): Promise<OpenAPIDeploymentOperationResponse> {
    return this.mutate('rollbackServiceDeployment', {
      path: { serviceId: projectId, deploymentId }, ...mutationRequest(options),
    });
  }

  start(projectId: string, environmentId: string, options: RuntimeOperationOptions): Promise<OpenAPIServiceOperationResponse> {
    return this.runtimeMutation('startServiceRuntime', projectId, environmentId, options);
  }

  stop(projectId: string, environmentId: string, options: RuntimeOperationOptions): Promise<OpenAPIServiceOperationResponse> {
    return this.runtimeMutation('stopServiceRuntime', projectId, environmentId, options);
  }

  restart(projectId: string, environmentId: string, options: RuntimeOperationOptions): Promise<OpenAPIServiceOperationResponse> {
    return this.runtimeMutation('restartServiceRuntime', projectId, environmentId, options);
  }

  forService(service: ServiceReference): ScopedServiceClient {
    validateReference(service);
    return new ScopedServiceClient(this, service);
  }

  private runtimeMutation(
    operation: 'startServiceRuntime' | 'stopServiceRuntime' | 'restartServiceRuntime',
    projectId: string,
    environmentId: string,
    options: RuntimeOperationOptions,
  ): Promise<OpenAPIServiceOperationResponse> {
    return this.mutate(operation, {
      path: { serviceId: projectId, environmentId },
      body: { expectedDeploymentId: options.expectedDeploymentId },
      ...mutationRequest(options),
    });
  }

  private listLogs(service: ServiceReference, options: ServiceLogOptions): Promise<OpenAPILogList> {
    return this.request('listServiceLogs', {
      path: servicePath(service),
      query: {
        kind: options.kind,
        environment: options.environmentId,
        deployment: options.deploymentId,
        limit: options.limit,
        cursor: options.cursor,
        follow: options.follow,
      },
      signal: options.signal,
    });
  }

  private async *followLogs(service: ServiceReference, options: ServiceLogOptions): AsyncGenerator<OpenAPILogEntry> {
    let cursor = options.cursor;
    while (true) {
      options.signal?.throwIfAborted();
      const page = await this.listLogs(service, { ...options, cursor, follow: true });
      cursor = page.nextCursor;
      for (const entry of page.items) {
        options.signal?.throwIfAborted();
        yield entry;
      }
      if (page.items.length === 0) {
        await abortableDelay(Math.max(1, page.pollAfterMs || this.followIntervalMs), options.signal);
      }
    }
  }

  private mutate<I extends Exclude<OpenAPIOperationId, 'getService' | 'getServiceDeployment' | 'getServiceStatus' | 'listServiceDeployments' | 'listServiceEnvironments' | 'listServiceLogs' | 'listServices' | 'previewServiceDeploy' | 'resolveService' | 'resolveServiceEnvironment'>>(
    operation: I,
    options: InternalRequestOptions,
  ): Promise<OpenAPIResponseBody<I>> {
    validateIdempotencyKey(options.idempotencyKey ?? '');
    return this.request(operation, options);
  }

  private async request<I extends OpenAPIOperationId>(operationId: I, options: InternalRequestOptions): Promise<OpenAPIResponseBody<I>> {
    const query = encodeQuery(options.query);
    const operation = resolveOpenAPIOperation(operationId, options.path, query);
    const endpoint = new URL(`${this.baseUrl.href.replace(/\/+$/, '')}${operation.path}`);
    const encodedBody = options.body === undefined ? undefined : JSON.stringify(options.body);
    const maxAttempts = this.retriesEnabled && (operation.method === 'GET' || options.idempotencyKey)
      ? this.retryPolicy.maxAttempts
      : 1;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      options.signal?.throwIfAborted();
      let response: Response;
      try {
        response = await this.fetchImpl(endpoint, {
          method: operation.method,
          headers: {
            Accept: 'application/json',
            Authorization: `Bearer ${this.token}`,
            ...(encodedBody === undefined ? {} : { 'Content-Type': 'application/json' }),
            ...(options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : {}),
          },
          body: encodedBody,
          redirect: 'manual',
          signal: options.signal,
        });
      } catch (error) {
        if (attempt < maxAttempts && !options.signal?.aborted) {
          await abortableDelay(jitter(attempt, this.retryPolicy.maxDelayMs), options.signal);
          continue;
        }
        throw error;
      }
      if (response.ok) return await decodeSuccess<I>(response);
      const apiError = await decodeError(response, this.retryPolicy.retryAfterMaxDelayMs);
      if (attempt < maxAttempts && RETRYABLE_STATUS.has(response.status)) {
        const retryAfterMs = response.status === 429 || response.status === 503
          ? apiError.retryAfterMs
          : undefined;
        await abortableDelay(retryAfterMs ?? jitter(attempt, this.retryPolicy.maxDelayMs), options.signal);
        continue;
      }
      throw apiError;
    }
    throw new Error('PostGrip Service request attempts exhausted');
  }
}

export class ScopedServiceClient {
  constructor(private readonly client: ServiceClient, readonly reference: ServiceReference) {}

  get(options: RequestOptions = {}): Promise<OpenAPIService> { return this.client.get(this.reference, options); }
  status(options: ServiceStatusOptions = {}): Promise<OpenAPIServiceStatus> { return this.client.status(this.reference, options); }
  environments(options: ListEnvironmentsOptions = {}): Promise<OpenAPIEnvironmentList> { return this.client.environments(this.reference, options); }
  deployments(options: ListDeploymentsOptions = {}): Promise<OpenAPIDeploymentList> { return this.client.deployments(this.reference, options); }
  check(options: CheckServiceOptions): Promise<OpenAPIServiceOperationResponse> { return this.client.check(this.reference, options); }
  readonly logs = {
    list: (options: ServiceLogOptions = {}) => this.client.logs.list(this.reference, options),
    follow: (options: ServiceLogOptions = {}) => this.client.logs.follow(this.reference, options),
  };
}

export function referenceFor(service: OpenAPIService): ServiceReference {
  return { source: service.source, id: service.id };
}

function servicePath(service: ServiceReference): Readonly<Record<string, string>> {
  validateReference(service);
  return { source: service.source, serviceId: service.id };
}

function validateReference(service: ServiceReference): void {
  if (service.source !== 'target' && service.source !== 'project') {
    throw new Error('service source must be target or project');
  }
  if (!service.id.trim()) throw new Error('service id is required');
}

function mutationRequest(options: MutationOptions): Pick<InternalRequestOptions, 'signal' | 'idempotencyKey'> {
  return { signal: options.signal, idempotencyKey: options.idempotencyKey };
}

function encodeQuery(query?: Readonly<Record<string, unknown>>): URLSearchParams | undefined {
  if (!query) return undefined;
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value == null) continue;
    result.set(key, String(value));
  }
  return result;
}

function validateIdempotencyKey(key: string): void {
  if (!/^[!-~]{1,128}$/.test(key)) {
    throw new Error('idempotencyKey must contain 1 to 128 visible ASCII characters');
  }
}

async function decodeSuccess<I extends OpenAPIOperationId>(response: Response): Promise<OpenAPIResponseBody<I>> {
  const body = await readBoundedResponseBody(response);
  return JSON.parse(body) as OpenAPIResponseBody<I>;
}

async function decodeError(response: Response, retryAfterMaxDelayMs: number): Promise<ServiceAPIError> {
  let value: Record<string, unknown> = {};
  try {
    const decoded: unknown = JSON.parse(await readBoundedResponseBody(response));
    if (typeof decoded === 'object' && decoded !== null && !Array.isArray(decoded)) {
      value = decoded as Record<string, unknown>;
    }
  } catch {
    // The typed fallback intentionally excludes the upstream response body.
  }
  return new ServiceAPIError(
    response.status,
    typeof value.code === 'string' ? value.code : 'HTTP_ERROR',
    typeof value.message === 'string' ? value.message : response.statusText,
    typeof value.requestId === 'string' ? value.requestId : response.headers.get('x-request-id') ?? '',
    typeof value.details === 'object' && value.details !== null ? value.details as Record<string, unknown> : undefined,
    parseRetryAfter(response.headers.get('retry-after'), retryAfterMaxDelayMs),
  );
}

async function readBoundedResponseBody(response: Response): Promise<string> {
  if (!response.body) return '';
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new Error('PostGrip Service response is invalid or too large');
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(body);
}

function parseRetryAfter(value: string | null, maximumMs: number): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds * 1_000, maximumMs);
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return undefined;
  return Math.min(Math.max(timestamp - Date.now(), 0), maximumMs);
}

function jitter(attempt: number, maximumMs: number): number {
  return Math.random() * Math.min(200 * 2 ** (attempt - 1), maximumMs);
}

function configuredRetryPolicy(config: ServiceRetryConfig = {}): RetryPolicy {
  const maxAttempts = config.maxAttempts ?? DEFAULT_RETRY_MAX_ATTEMPTS;
  const maxDelayMs = config.maxDelayMs ?? DEFAULT_RETRY_MAX_DELAY_MS;
  const retryAfterMaxDelayMs = config.retryAfterMaxDelayMs ?? DEFAULT_RETRY_AFTER_MAX_DELAY_MS;
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > MAXIMUM_RETRY_MAX_ATTEMPTS) {
    throw new Error(`PostGrip Service retry maxAttempts must be an integer from 1 to ${MAXIMUM_RETRY_MAX_ATTEMPTS}`);
  }
  if (!Number.isFinite(maxDelayMs) || maxDelayMs <= 0 || maxDelayMs > MAXIMUM_RETRY_MAX_DELAY_MS) {
    throw new Error(`PostGrip Service retry maxDelayMs must be greater than 0 and at most ${MAXIMUM_RETRY_MAX_DELAY_MS}`);
  }
  if (!Number.isFinite(retryAfterMaxDelayMs) || retryAfterMaxDelayMs <= 0 || retryAfterMaxDelayMs > MAXIMUM_RETRY_AFTER_MAX_DELAY_MS) {
    throw new Error(`PostGrip Service retry retryAfterMaxDelayMs must be greater than 0 and at most ${MAXIMUM_RETRY_AFTER_MAX_DELAY_MS}`);
  }
  return { maxAttempts, maxDelayMs, retryAfterMaxDelayMs };
}

function processEnvironment(): Readonly<Record<string, string | undefined>> {
  return (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
}

function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const complete = () => {
      signal?.removeEventListener('abort', abort);
      resolve();
    };
    const abort = () => {
      clearTimeout(timer);
      reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(complete, milliseconds);
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, { once: true });
  });
}
