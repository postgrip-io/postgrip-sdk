import { readBoundedResponseBody } from './http.js';
import { abortableDelay } from './polling.js';

/** Default bound on one ordinary HTTP exchange, as in every SDK language. */
export const DEFAULT_TIMEOUT_MS = 30_000;

/** The largest delay `setTimeout` honors; Node and Bun clamp larger values to 1 ms. */
const MAX_TIMEOUT_MS = 2_147_483_647;

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);

/** Lanes that carry the management bearer. */
const MANAGEMENT_LANES = new Set(['management', 'worker-management', 'service-management']);

/**
 * The decoded common error envelope. Plane errors extend it, so callers can
 * read status, code, message, request ID, details and retry-after uniformly.
 */
export class PostGripAPIError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly details?: Readonly<Record<string, unknown>>,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = 'PostGripAPIError';
  }
}

/**
 * One failed exchange, from which a plane builds its typed error. `message` is
 * the envelope message or the status text, and `responseBody` the bounded raw
 * body; both are server content, so a plane whose text must exclude it uses
 * `method`, `route` and `status` instead.
 */
export interface APIErrorFields {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly requestId: string;
  readonly details?: Readonly<Record<string, unknown>>;
  readonly retryAfterMs?: number;
  readonly method: string;
  readonly route: string;
  readonly responseBody: string;
}

/** The contract annotations of one resolved generated operation. */
export interface TransportOperation {
  readonly id: string;
  readonly method: string;
  readonly path: string;
  readonly authLane: string;
  readonly safety: string;
  readonly idempotency: string;
  readonly retry: string;
  readonly signing?: string;
  readonly headerParameters: readonly string[];
  readonly streamingRequest: boolean;
  readonly webSocket: boolean;
}

export interface RetryConfig {
  readonly enabled: boolean;
  readonly maxAttempts: number;
  readonly maxDelayMs: number;
  readonly retryAfterMaxDelayMs: number;
}

/** Delegated runtime credentials for the `agent` and `either` lanes. */
export interface DelegatedCredentials {
  /** Whether delegated credentials are configured; the `either` lane prefers them when true. */
  hasDelegated(): boolean;
  /**
   * Returns the current delegated access token, refreshing it when needed. The
   * executor calls it immediately before every network attempt, including retries.
   */
  delegated(signal: AbortSignal | undefined): Promise<string>;
}

/** The final request of a signed operation, over the exact encoded body bytes. */
export interface SignableRequest {
  readonly method: string;
  readonly url: URL;
  readonly headers: Headers;
  readonly body: Uint8Array;
}

export interface ExecutorConfig {
  /** The plane name used in local error messages, such as `Worker`. */
  readonly plane: string;
  readonly baseUrl: URL;
  readonly fetch: typeof globalThis.fetch;
  /** Sent as the bearer on the management lanes, and on `either` without delegated credentials. */
  readonly managementToken?: string;
  readonly delegatedCredentials?: DelegatedCredentials;
  /**
   * Headers configured on the plane connection. They replace the executor's
   * own value for the same name, and an `Authorization` among them keeps
   * precedence on management lanes. Public lanes never send one.
   */
  readonly headers?: HeadersInit;
  readonly retry: RetryConfig;
  /** Bound on each exchange; an earlier caller abort still wins. */
  readonly timeoutMs: number;
  readonly maxResponseBytes?: number;
  /** Larger bounds for successful responses of named operations. */
  readonly successResponseBytes?: Readonly<Partial<Record<string, number>>>;
  /** Signs the final request of an operation that declares signing. The executor never holds the key. */
  readonly sign?: (request: SignableRequest) => Promise<void>;
  /** Builds the plane's error type, which owns the default error text. */
  readonly createError: (fields: APIErrorFields) => PostGripAPIError;
}

export interface ExecutorCall {
  readonly operation: TransportOperation;
  readonly body?: unknown;
  readonly idempotencyKey?: string;
  readonly ifMatch?: string;
  readonly signal?: AbortSignal;
  /** Non-2xx statuses the plane adapter handles; their bounded raw body is returned. */
  readonly acceptedStatuses?: readonly number[];
  /** Raises this exchange's lifetime, for example for a long poll's server hold. It never lowers it. */
  readonly lifetimeMs?: number;
  /**
   * Otherwise retryable statuses this call never retries, such as an answer the
   * server does not keep against the idempotency key, after which a resend
   * repeats the operation's side effect.
   */
  readonly noRetryStatuses?: readonly number[];
}

/** The bounded raw response of a successful or accepted exchange. */
export interface ExchangeResponse {
  readonly status: number;
  readonly headers: Headers;
  readonly body: string;
}

/**
 * Runs generated operations under their contract annotations: auth lane,
 * idempotency and declared preconditions, signing, a bounded lifetime, manual
 * redirects, opt-in bounded retry, response bounds and envelope errors.
 */
export class Executor {
  constructor(private readonly config: ExecutorConfig) {}

  /** Runs one operation and decodes its successful JSON body. */
  async request<T>(call: ExecutorCall): Promise<T> {
    return JSON.parse((await this.exchange(call)).body) as T;
  }

  /** Runs one operation and returns the bounded raw body of a successful or accepted response. */
  async exchange(call: ExecutorCall): Promise<ExchangeResponse> {
    const { operation } = call;
    const { plane } = this.config;
    if (operation.streamingRequest || operation.webSocket) {
      throw new Error(`PostGrip ${plane} operation ${operation.id} requires its protocol adapter`);
    }
    if (operation.signing && !this.config.sign) {
      throw new Error(`PostGrip ${plane} operation ${operation.id} requires request signing`);
    }
    const delegated = this.delegatedLane(operation);
    // A required key must be valid; an optional one is checked only when the
    // caller sends it, and is never generated.
    if (operation.idempotency === 'required' || (operation.idempotency === 'optional' && call.idempotencyKey)) {
      validateIdempotencyKey(call.idempotencyKey);
    }
    const endpoint = new URL(`${this.config.baseUrl.href.replace(/\/+$/, '')}${operation.path}`);
    const encodedBody = call.body === undefined ? undefined : JSON.stringify(call.body);
    const bodyBytes = new TextEncoder().encode(encodedBody ?? '');

    const { retry } = this.config;
    // Protocol and signed operations are never retried, even if mis-annotated as bounded.
    const eligible = retry.enabled && operation.retry === 'bounded' && operation.safety !== 'protocol' && !operation.signing
      && (operation.safety === 'read-only' || Boolean(call.idempotencyKey));
    const maxAttempts = eligible ? retry.maxAttempts : 1;
    const lifetimeMs = Math.min(Math.max(this.config.timeoutMs, call.lifetimeMs ?? 0), MAX_TIMEOUT_MS);
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      call.signal?.throwIfAborted();
      // A credential or signing failure happens before sending, so it is never retried.
      const headers = await this.requestHeaders(call, encodedBody !== undefined, delegated);
      if (operation.signing) {
        await this.config.sign?.({ method: operation.method, url: endpoint, headers, body: bodyBytes });
      }
      call.signal?.throwIfAborted();
      const lifetime = boundedSignal(call.signal, lifetimeMs, plane);
      try {
        let response: Response;
        try {
          response = await this.config.fetch(endpoint, {
            method: operation.method,
            headers,
            body: encodedBody,
            redirect: 'manual',
            signal: lifetime.signal,
          });
        } catch (error) {
          if (attempt < maxAttempts && !call.signal?.aborted) {
            await abortableDelay(jitter(attempt, retry.maxDelayMs), call.signal);
            continue;
          }
          throw error;
        }
        if (response.ok) {
          const limit = this.config.successResponseBytes?.[operation.id] ?? this.config.maxResponseBytes;
          return { status: response.status, headers: response.headers, body: await readBoundedResponseBody(response, plane, limit) };
        }
        if (call.acceptedStatuses?.includes(response.status)) {
          return {
            status: response.status,
            headers: response.headers,
            body: await readBoundedResponseBody(response, plane, this.config.maxResponseBytes),
          };
        }
        const apiError = await this.decodeError(operation, response, lifetime.signal);
        if (attempt < maxAttempts && RETRYABLE_STATUS.has(response.status) && !call.noRetryStatuses?.includes(response.status)) {
          const retryAfterMs = response.status === 429 || response.status === 503 ? apiError.retryAfterMs : undefined;
          await abortableDelay(retryAfterMs ?? jitter(attempt, retry.maxDelayMs), call.signal);
          continue;
        }
        throw apiError;
      } finally {
        lifetime.clear();
      }
    }
    throw new Error(`PostGrip ${plane} request attempts exhausted`);
  }

  /** Fixes the credential class for every attempt of one call. */
  private delegatedLane(operation: TransportOperation): boolean {
    const credentials = this.config.delegatedCredentials;
    switch (operation.authLane) {
      case 'agent':
        if (!credentials) {
          throw new Error(`PostGrip ${this.config.plane} operation ${operation.id} requires delegated runtime credentials`);
        }
        return true;
      case 'either':
        return credentials?.hasDelegated() ?? false;
      case 'public':
        return false;
      default:
        if (MANAGEMENT_LANES.has(operation.authLane)) return false;
        throw new Error(`PostGrip ${this.config.plane} operation ${operation.id} uses unsupported auth lane ${operation.authLane}`);
    }
  }

  private async requestHeaders(call: ExecutorCall, hasBody: boolean, delegated: boolean): Promise<Headers> {
    const { operation } = call;
    const headers = new Headers({ Accept: 'application/json' });
    if (hasBody) headers.set('Content-Type', 'application/json');
    new Headers(this.config.headers).forEach((value, name) => headers.set(name, value));
    if (call.idempotencyKey && operation.headerParameters.includes('Idempotency-Key')) {
      headers.set('Idempotency-Key', call.idempotencyKey);
    }
    if (call.ifMatch && operation.headerParameters.includes('If-Match')) headers.set('If-Match', call.ifMatch);
    if (!operation.headerParameters.includes('If-Match')) headers.delete('If-Match');
    if (operation.authLane === 'public') {
      headers.delete('Authorization');
    } else if (delegated) {
      const token = await this.config.delegatedCredentials?.delegated(call.signal);
      if (!token) throw new Error(`PostGrip ${this.config.plane} delegated runtime credential is empty`);
      headers.set('Authorization', `Bearer ${token}`);
    } else if (this.config.managementToken && !headers.has('Authorization')) {
      // A configured Authorization header keeps its precedence on management lanes.
      headers.set('Authorization', `Bearer ${this.config.managementToken}`);
    }
    return headers;
  }

  private async decodeError(operation: TransportOperation, response: Response, lifetime: AbortSignal): Promise<PostGripAPIError> {
    let body = '';
    try {
      body = await readBoundedResponseBody(response, this.config.plane, this.config.maxResponseBytes);
    } catch {
      // A timeout or caller abort while reading the body stays the failure,
      // as it does for a success body.
      if (lifetime.aborted) throw lifetime.reason;
      // Otherwise an unreadable or oversized error body decodes as empty.
    }
    return this.config.createError(
      apiErrorFields(response, body, operation.method, operation.path, this.config.retry.retryAfterMaxDelayMs),
    );
  }
}

/**
 * Decodes the common error envelope of a failed response whose bounded body
 * has been read, for the executor and for adapters that send their own requests.
 */
export function apiErrorFields(
  response: Response,
  body: string,
  method: string,
  route: string,
  retryAfterMaxDelayMs: number,
): APIErrorFields {
  let value: Record<string, unknown> = {};
  try {
    const decoded: unknown = JSON.parse(body);
    if (typeof decoded === 'object' && decoded !== null && !Array.isArray(decoded)) {
      value = decoded as Record<string, unknown>;
    }
  } catch {
    // The typed fallback excludes the upstream body from the decoded fields.
  }
  return {
    status: response.status,
    code: typeof value.code === 'string' ? value.code : 'HTTP_ERROR',
    message: typeof value.message === 'string' ? value.message : response.statusText,
    requestId: typeof value.requestId === 'string' ? value.requestId : response.headers.get('x-request-id') ?? '',
    details: typeof value.details === 'object' && value.details !== null ? value.details as Record<string, unknown> : undefined,
    retryAfterMs: parseRetryAfter(response.headers.get('retry-after'), retryAfterMaxDelayMs),
    method,
    route,
    responseBody: body,
  };
}

/** Rejects an idempotency key that is missing or not 1 to 128 visible ASCII characters. */
export function validateIdempotencyKey(key: string | undefined): void {
  if (key === undefined || !/^[!-~]{1,128}$/.test(key)) {
    throw new Error('idempotencyKey must contain 1 to 128 visible ASCII characters');
  }
}

/**
 * Validates a configured exchange timeout, defaulting to 30 seconds. A value
 * above the platform timer limit is rejected rather than firing almost at once.
 */
export function configuredTimeoutMs(plane: string, value: number | undefined): number {
  const timeoutMs = value ?? DEFAULT_TIMEOUT_MS;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > MAX_TIMEOUT_MS) {
    throw new Error(`PostGrip ${plane} timeoutMs must be a positive number of milliseconds up to ${MAX_TIMEOUT_MS}`);
  }
  return timeoutMs;
}

/**
 * Parses `Retry-After` as non-negative delta-seconds or an HTTP date, capped at
 * `maximumMs`. A signed or otherwise invalid value is ignored, so the jittered
 * backoff applies.
 */
export function parseRetryAfter(value: string | null, maximumMs: number): number | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  if (/^\d+$/.test(trimmed)) return Math.min(Number(trimmed) * 1_000, maximumMs);
  if (!/[A-Za-z]/.test(trimmed)) return undefined;
  const timestamp = Date.parse(trimmed);
  if (Number.isNaN(timestamp)) return undefined;
  return Math.min(Math.max(timestamp - Date.now(), 0), maximumMs);
}

function jitter(attempt: number, maximumMs: number): number {
  return Math.random() * Math.min(200 * 2 ** (attempt - 1), maximumMs);
}

/**
 * A signal that aborts with the caller's reason when the caller aborts, or
 * with a TimeoutError after `timeoutMs`. `clear` releases the timer once the
 * exchange, including its body read, has finished.
 */
function boundedSignal(
  caller: AbortSignal | undefined,
  timeoutMs: number,
  plane: string,
): { readonly signal: AbortSignal; clear(): void } {
  const controller = new AbortController();
  const onAbort = () => controller.abort(caller?.reason);
  caller?.addEventListener('abort', onAbort, { once: true });
  // The caller may have aborted while credentials or signing were awaited.
  if (caller?.aborted) onAbort();
  const timer = setTimeout(() => {
    controller.abort(new DOMException(`PostGrip ${plane} request timed out after ${timeoutMs}ms`, 'TimeoutError'));
  }, timeoutMs);
  return {
    signal: controller.signal,
    clear() {
      clearTimeout(timer);
      caller?.removeEventListener('abort', onAbort);
    },
  };
}
