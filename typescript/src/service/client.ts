import {
  OpenAPIClient,
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
  type OpenAPIQueryParameters,
  type OpenAPIRequestBody,
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
import { validateBaseUrl, validateManagementToken, type PostGripEnvironment } from '../internal/config.js';
import { readBoundedResponseBody } from '../internal/http.js';

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);
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
  readonly environment?: PostGripEnvironment;
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

export interface AdministrationWriteOptions extends MutationOptions {
  readonly ifMatch: string;
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
  readonly query?: Readonly<Record<string, unknown>> | URLSearchParams;
  readonly body?: unknown;
  readonly signal?: AbortSignal;
  readonly idempotencyKey?: string;
  readonly ifMatch?: string;
}

interface RetryPolicy {
  readonly maxAttempts: number;
  readonly maxDelayMs: number;
  readonly retryAfterMaxDelayMs: number;
}

export class ServiceClient {
  readonly openapi: OpenAPIClient;
  readonly logs = {
    list: (service: ServiceReference, options: ServiceLogOptions = {}) => this.listLogs(service, options),
    follow: (service: ServiceReference, options: ServiceLogOptions = {}) => this.followLogs(service, options),
  };

  readonly administration = {
    targets: {
      attach: (body: OpenAPIRequestBody<'attachTargetService'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('attachTargetService', { body, ...administrationWrite(options) }, true),
      update: (serviceId: string, body: OpenAPIRequestBody<'updateTargetService'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateTargetService', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      removalImpact: (serviceId: string, options: RequestOptions = {}) =>
        this.request('getTargetServiceRemovalImpact', { path: { serviceId }, signal: options.signal }),
      detach: (serviceId: string, body: OpenAPIRequestBody<'detachTargetService'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('detachTargetService', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      putConnection: (serviceId: string, body: OpenAPIRequestBody<'putTargetServiceConnection'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('putTargetServiceConnection', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      clearConnection: (serviceId: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('clearTargetServiceConnection', { path: { serviceId }, ...administrationWrite(options) }, true),
    },
    projects: {
      create: (body: OpenAPIRequestBody<'createServiceProject'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('createServiceProject', { body, ...administrationWrite(options) }, true),
      update: (serviceId: string, body: OpenAPIRequestBody<'updateServiceProject'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceProject', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      removalImpact: (serviceId: string, options: RequestOptions = {}) =>
        this.request('getServiceProjectRemovalImpact', { path: { serviceId }, signal: options.signal }),
      delete: (serviceId: string, body: OpenAPIRequestBody<'deleteServiceProject'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('deleteServiceProject', { path: { serviceId }, body, ...administrationWrite(options) }, true),
    },
    environments: {
      get: (serviceId: string, environmentId: string, options: RequestOptions = {}) =>
        this.request('getServiceEnvironment', { path: { serviceId, environmentId }, signal: options.signal }),
      create: (serviceId: string, body: OpenAPIRequestBody<'createServiceEnvironment'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('createServiceEnvironment', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      update: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'updateServiceEnvironment'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceEnvironment', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
      previewReassignment: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'previewServiceEnvironmentReassignment'>, options: MutationOptions) =>
        this.administrationMutation('previewServiceEnvironmentReassignment', { path: { serviceId, environmentId }, body, ...mutationRequest(options) }),
      reassign: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'reassignServiceEnvironment'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('reassignServiceEnvironment', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
      removalImpact: (serviceId: string, environmentId: string, options: RequestOptions = {}) =>
        this.request('getServiceEnvironmentRemovalImpact', { path: { serviceId, environmentId }, signal: options.signal }),
      delete: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'deleteServiceEnvironment'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('deleteServiceEnvironment', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
    },
    volumes: {
      list: (serviceId: string, options: RequestOptions = {}) => this.request('listServiceVolumes', { path: { serviceId }, signal: options.signal }),
      create: (serviceId: string, body: OpenAPIRequestBody<'createServiceVolume'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('createServiceVolume', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      get: (serviceId: string, volumeRef: string, options: RequestOptions = {}) => this.request('getServiceVolume', { path: { serviceId, volumeRef }, signal: options.signal }),
      removalImpact: (serviceId: string, volumeRef: string, options: RequestOptions = {}) => this.request('getServiceVolumeRemovalImpact', { path: { serviceId, volumeRef }, signal: options.signal }),
      delete: (serviceId: string, volumeRef: string, body: OpenAPIRequestBody<'deleteServiceVolume'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('deleteServiceVolume', { path: { serviceId, volumeRef }, body, ...administrationWrite(options) }, true),
      bind: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'bindServiceVolume'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('bindServiceVolume', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
      updateBinding: (serviceId: string, environmentId: string, volumeRef: string, body: OpenAPIRequestBody<'updateServiceVolumeBinding'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceVolumeBinding', { path: { serviceId, environmentId, volumeRef }, body, ...administrationWrite(options) }, true),
      unbind: (serviceId: string, environmentId: string, volumeRef: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('unbindServiceVolume', { path: { serviceId, environmentId, volumeRef }, ...administrationWrite(options) }, true),
    },
    domains: {
      list: (serviceId: string, environmentId: string, options: RequestOptions = {}) => this.request('listServiceDomains', { path: { serviceId, environmentId }, signal: options.signal }),
      create: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'createServiceDomain'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('createServiceDomain', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
      update: (serviceId: string, environmentId: string, domainId: string, body: OpenAPIRequestBody<'updateServiceDomain'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceDomain', { path: { serviceId, environmentId, domainId }, body, ...administrationWrite(options) }, true),
      delete: (serviceId: string, environmentId: string, domainId: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('deleteServiceDomain', { path: { serviceId, environmentId, domainId }, ...administrationWrite(options) }, true),
    },
    variables: {
      list: (serviceId: string, environmentId: string, options: RequestOptions = {}) => this.request('listServiceVariables', { path: { serviceId, environmentId }, signal: options.signal }),
      create: (serviceId: string, environmentId: string, body: OpenAPIRequestBody<'createServiceVariable'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('createServiceVariable', { path: { serviceId, environmentId }, body, ...administrationWrite(options) }, true),
      update: (serviceId: string, environmentId: string, variableId: string, body: OpenAPIRequestBody<'updateServiceVariable'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceVariable', { path: { serviceId, environmentId, variableId }, body, ...administrationWrite(options) }, true),
      delete: (serviceId: string, environmentId: string, variableId: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('deleteServiceVariable', { path: { serviceId, environmentId, variableId }, ...administrationWrite(options) }, true),
      putValue: (serviceId: string, environmentId: string, variableId: string, body: OpenAPIRequestBody<'putServiceVariableValue'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('putServiceVariableValue', { path: { serviceId, environmentId, variableId }, body, ...administrationWrite(options) }, true),
      clearValue: (serviceId: string, environmentId: string, variableId: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('clearServiceVariableValue', { path: { serviceId, environmentId, variableId }, ...administrationWrite(options) }, true),
      apply: (serviceId: string, body: OpenAPIRequestBody<'applyServiceVariables'>, options: MutationOptions) =>
        this.administrationMutation('applyServiceVariables', { path: { serviceId }, body, ...mutationRequest(options) }),
    },
    repositories: {
      get: (serviceId: string, options: RequestOptions = {}) => this.request('getServiceRepository', { path: { serviceId }, signal: options.signal }),
      update: (serviceId: string, body: OpenAPIRequestBody<'updateServiceRepository'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceRepository', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      putCredential: (serviceId: string, credentialKind: string, body: OpenAPIRequestBody<'putServiceRepositoryCredential'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('putServiceRepositoryCredential', { path: { serviceId, credentialKind }, body, ...administrationWrite(options) }, true),
      clearCredential: (serviceId: string, credentialKind: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('clearServiceRepositoryCredential', { path: { serviceId, credentialKind }, ...administrationWrite(options) }, true),
      refreshCredential: (serviceId: string, credentialKind: string, options: AdministrationWriteOptions) =>
        this.administrationMutation('refreshServiceRepositoryCredential', { path: { serviceId, credentialKind }, ...administrationWrite(options) }, true),
    },
    promotions: {
      list: (serviceId: string, query: OpenAPIQueryParameters<'listServicePromotions'> = {}, options: RequestOptions = {}) => this.request('listServicePromotions', { path: { serviceId }, query, signal: options.signal }),
      preview: (serviceId: string, query: OpenAPIQueryParameters<'previewServicePromotion'>, options: RequestOptions = {}) => this.request('previewServicePromotion', { path: { serviceId }, query, signal: options.signal }),
      create: (serviceId: string, body: OpenAPIRequestBody<'promoteServiceDeployment'>, options: MutationOptions) =>
        this.administrationMutation('promoteServiceDeployment', { path: { serviceId }, body, ...mutationRequest(options) }),
    },
    retention: {
      getBuild: (serviceId: string, options: RequestOptions = {}) => this.request('getServiceBuildLogSettings', { path: { serviceId }, signal: options.signal }),
      updateBuild: (serviceId: string, body: OpenAPIRequestBody<'updateServiceBuildLogSettings'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceBuildLogSettings', { path: { serviceId }, body, ...administrationWrite(options) }, true),
      trimBuild: (serviceId: string, options: AdministrationWriteOptions) => this.administrationMutation('trimServiceBuildLogs', { path: { serviceId }, ...administrationWrite(options) }, true),
      flushBuild: (serviceId: string, options: AdministrationWriteOptions) => this.administrationMutation('flushServiceBuildLogs', { path: { serviceId }, ...administrationWrite(options) }, true),
      getRuntime: (serviceId: string, query: OpenAPIQueryParameters<'getServiceRuntimeLogSettings'> = {}, options: RequestOptions = {}) => this.request('getServiceRuntimeLogSettings', { path: { serviceId }, query, signal: options.signal }),
      updateRuntime: (serviceId: string, query: OpenAPIQueryParameters<'updateServiceRuntimeLogSettings'>, body: OpenAPIRequestBody<'updateServiceRuntimeLogSettings'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('updateServiceRuntimeLogSettings', { path: { serviceId }, query, body, ...administrationWrite(options) }, true),
      trimRuntime: (serviceId: string, query: OpenAPIQueryParameters<'trimServiceRuntimeLogs'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('trimServiceRuntimeLogs', { path: { serviceId }, query, ...administrationWrite(options) }, true),
      flushRuntime: (serviceId: string, query: OpenAPIQueryParameters<'flushServiceRuntimeLogs'>, options: AdministrationWriteOptions) =>
        this.administrationMutation('flushServiceRuntimeLogs', { path: { serviceId }, query, ...administrationWrite(options) }, true),
    },
    configurationOperations: {
      list: (query: OpenAPIQueryParameters<'listServiceConfigurationOperations'> = {}, options: RequestOptions = {}) => this.request('listServiceConfigurationOperations', { query, signal: options.signal }),
      get: (operationId: string, options: RequestOptions = {}) => this.request('getServiceConfigurationOperation', { path: { operationId }, signal: options.signal }),
      retry: (operationId: string, options: AdministrationWriteOptions) => this.administrationMutation('retryServiceConfigurationOperation', { path: { operationId }, ...administrationWrite(options) }, true),
    },
    declarativeConfiguration: {
      validate: (body: OpenAPIRequestBody<'validatePostGripConfiguration'>, options: RequestOptions = {}) =>
        this.request('validatePostGripConfiguration', { body, signal: options.signal }),
      getStack: (stackKey: string, options: RequestOptions = {}) =>
        this.request('getPostGripConfigurationStack', { path: { stackKey }, signal: options.signal }),
      createPlan: (stackKey: string, body: OpenAPIRequestBody<'createPostGripConfigurationPlan'>, options: MutationOptions) =>
        this.administrationMutation('createPostGripConfigurationPlan', { path: { stackKey }, body, ...mutationRequest(options) }),
      getPlan: (stackKey: string, planId: string, options: RequestOptions = {}) =>
        this.request('getPostGripConfigurationPlan', { path: { stackKey, planId }, signal: options.signal }),
      listActions: (stackKey: string, planId: string, query: OpenAPIQueryParameters<'listPostGripConfigurationPlanActions'> = {}, options: RequestOptions = {}) =>
        this.request('listPostGripConfigurationPlanActions', { path: { stackKey, planId }, query, signal: options.signal }),
    },
  };

  private readonly baseUrl: URL;
  private readonly token: string;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly retriesEnabled: boolean;
  private readonly retryPolicy: RetryPolicy;
  private readonly followIntervalMs: number;

  constructor(config: ServiceClientConfig) {
    this.baseUrl = validateBaseUrl('Service', config.baseUrl, config.insecureDevelopment);
    this.token = validateManagementToken(config.token);
    this.fetchImpl = config.fetch ?? globalThis.fetch;
    this.retriesEnabled = config.enableRetries ?? false;
    this.retryPolicy = configuredRetryPolicy(config.retry);
    this.followIntervalMs = Math.max(1, config.followIntervalMs ?? 2_000);
    this.openapi = new OpenAPIClient((id, options) => {
      const headers = options.headers as Readonly<Record<string, string>> | undefined;
      return this.request(id, {
        path: options.pathParameters as Readonly<Record<string, string>> | undefined,
        query: options.query,
        body: options.body,
        signal: options.signal,
        idempotencyKey: headers?.['Idempotency-Key'],
        ifMatch: headers?.['If-Match'],
      });
    });
  }

  static fromEnv(config: ServiceClientEnvironmentConfig = {}): ServiceClient {
    const { environment = process.env, ...overrides } = config;
    return new ServiceClient({
      ...overrides,
      baseUrl: environment.POSTGRIP_SERVICE_URL ?? environment.POSTGRIP_URL ?? '',
      token: environment.POSTGRIP_TOKEN ?? '',
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

  private administrationMutation<I extends OpenAPIOperationId>(
    operation: I,
    options: InternalRequestOptions,
    conditional = false,
  ): Promise<OpenAPIResponseBody<I>> {
    validateIdempotencyKey(options.idempotencyKey ?? '');
    if (conditional) validateETag(options.ifMatch ?? '');
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
            ...(options.ifMatch ? { 'If-Match': options.ifMatch } : {}),
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

function administrationWrite(options: AdministrationWriteOptions): Pick<InternalRequestOptions, 'signal' | 'idempotencyKey' | 'ifMatch'> {
  return { signal: options.signal, idempotencyKey: options.idempotencyKey, ifMatch: options.ifMatch };
}

function encodeQuery(query?: Readonly<Record<string, unknown>> | URLSearchParams): URLSearchParams | undefined {
  if (!query) return undefined;
  if (query instanceof URLSearchParams) return query;
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

function validateETag(value: string): void {
  if (!value.trim() || /[\r\n]/.test(value)) {
    throw new Error('If-Match ETag must be non-empty and contain no line breaks');
  }
}

async function decodeSuccess<I extends OpenAPIOperationId>(response: Response): Promise<OpenAPIResponseBody<I>> {
  const body = await readBoundedResponseBody(response, 'Service');
  return JSON.parse(body) as OpenAPIResponseBody<I>;
}

async function decodeError(response: Response, retryAfterMaxDelayMs: number): Promise<ServiceAPIError> {
  let value: Record<string, unknown> = {};
  try {
    const decoded: unknown = JSON.parse(await readBoundedResponseBody(response, 'Service'));
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
