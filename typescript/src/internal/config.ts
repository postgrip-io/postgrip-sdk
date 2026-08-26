export interface PostGripEnvironment {
  readonly POSTGRIP_URL?: string;
  readonly POSTGRIP_AGENT_URL?: string;
  readonly POSTGRIP_WORKER_URL?: string;
  readonly POSTGRIP_SERVICE_URL?: string;
  readonly POSTGRIP_TOKEN?: string;
}

export interface ResolvedPostGripConfig {
  readonly agentUrl: string;
  readonly workerUrl: string;
  readonly serviceUrl: string;
  readonly token: string;
}

export function resolvePostGripConfig(options: {
  readonly baseUrl?: string;
  readonly agentUrl?: string;
  readonly workerUrl?: string;
  readonly serviceUrl?: string;
  readonly token?: string;
  readonly environment?: PostGripEnvironment;
}): ResolvedPostGripConfig {
  const environment = options.environment ?? process.env;
  const baseUrl = first(options.baseUrl, environment.POSTGRIP_URL);
  return {
    agentUrl: requiredUrl('Agent', first(options.agentUrl, environment.POSTGRIP_AGENT_URL, baseUrl)),
    workerUrl: requiredUrl('Worker', first(options.workerUrl, environment.POSTGRIP_WORKER_URL, baseUrl)),
    serviceUrl: requiredUrl('Service', first(options.serviceUrl, environment.POSTGRIP_SERVICE_URL, baseUrl)),
    token: validateManagementToken(first(options.token, environment.POSTGRIP_TOKEN)),
  };
}

export function validateManagementToken(value: string | undefined): string {
  const token = value?.trim() ?? '';
  if (!token.startsWith('pgt_')) {
    throw new Error('PostGrip token must use the pgt_ prefix');
  }
  return token;
}

export function validateBaseUrl(
  plane: string,
  value: string,
  insecureDevelopment = false,
): URL {
  const raw = value.trim();
  const baseUrl = new URL(raw);
  if (baseUrl.protocol !== 'https:' && !(insecureDevelopment && baseUrl.protocol === 'http:')) {
    throw new Error(`PostGrip ${plane} baseUrl must use HTTPS unless insecureDevelopment is enabled`);
  }
  if (/[?#]/.test(raw) || baseUrl.search || baseUrl.hash) {
    throw new Error(`PostGrip ${plane} baseUrl must not contain a query or fragment`);
  }
  return baseUrl;
}

function requiredUrl(plane: string, value: string | undefined): string {
  if (!value) throw new Error(`PostGrip ${plane} URL is required; configure POSTGRIP_URL or POSTGRIP_${plane.toUpperCase()}_URL`);
  return value;
}

function first(...values: Array<string | undefined>): string | undefined {
  return values.map((value) => value?.trim()).find(Boolean);
}
