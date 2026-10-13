import { readBoundedResponseBody } from './http.js';
import { abortableDelay } from './polling.js';

/** Default bound on one ordinary HTTP exchange, as in every SDK language. */
export const DEFAULT_TIMEOUT_MS = 30_000;

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);

/** Lanes that carry the management bearer. `agent` and `either` need the Agent credential hook. */
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

export interface ExecutorConfig {
  /** The plane name used in local error messages, such as `Worker`. */
  readonly plane: string;
  readonly baseUrl: URL;
  readonly fetch: typeof globalThis.fetch;
  /** Sent as the bearer on the management lanes. */
  readonly managementToken: string;
  readonly retry: RetryConfig;
  /** Bound on each exchange; an earlier caller abort still wins. */
  readonly timeoutMs: number;
  readonly maxResponseBytes?: number;
  /** Larger bounds for successful responses of named operations. */
  readonly successResponseBytes?: Readonly<Partial<Record<string, number>>>;
  /** Builds the plane's error type, which owns the default error text. */
  readonly createError: (
    status: number,
    code: string,
    message: string,
    requestId: string,
    details: Readonly<Record<string, unknown>> | undefined,
    retryAfterMs: number | undefined,
  ) => PostGripAPIError;
}

export interface ExecutorCall {
  readonly operation: TransportOperation;
  readonly body?: unknown;
  readonly idempotencyKey?: string;
  readonly ifMatch?: string;
  readonly signal?: AbortSignal;
}

/**
 * Runs generated operations under their contract annotations: auth lane,
 * idempotency and declared preconditions, a bounded lifetime, manual
 * redirects, opt-in bounded retry, response bounds and envelope errors.
 */
export class Executor {
  constructor(private readonly config: ExecutorConfig) {}

  async request<T>(call: ExecutorCall): Promise<T> {
    const { operation } = call;
    if (operation.streamingRequest || operation.webSocket || operation.signing) {
      throw new Error(`PostGrip ${this.config.plane} operation ${operation.id} requires its protocol adapter`);
    }
    if (operation.authLane !== 'public' && !MANAGEMENT_LANES.has(operation.authLane)) {
      throw new Error(`PostGrip ${this.config.plane} operation ${operation.id} uses unsupported auth lane ${operation.authLane}`);
    }
    if (operation.idempotency === 'required') {
      validateIdempotencyKey(call.idempotencyKey);
    }
    const endpoint = new URL(`${this.config.baseUrl.href.replace(/\/+$/, '')}${operation.path}`);
    const encodedBody = call.body === undefined ? undefined : JSON.stringify(call.body);
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (encodedBody !== undefined) headers['Content-Type'] = 'application/json';
    if (MANAGEMENT_LANES.has(operation.authLane)) headers.Authorization = `Bearer ${this.config.managementToken}`;
    if (call.idempotencyKey && operation.headerParameters.includes('Idempotency-Key')) {
      headers['Idempotency-Key'] = call.idempotencyKey;
    }
    if (call.ifMatch && operation.headerParameters.includes('If-Match')) headers['If-Match'] = call.ifMatch;

    const { retry } = this.config;
    // Protocol operations are never retried, even if mis-annotated as bounded.
    const eligible = retry.enabled && operation.retry === 'bounded' && operation.safety !== 'protocol'
      && (operation.safety === 'read-only' || Boolean(call.idempotencyKey));
    const maxAttempts = eligible ? retry.maxAttempts : 1;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      call.signal?.throwIfAborted();
      const lifetime = boundedSignal(call.signal, this.config.timeoutMs, this.config.plane);
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
          return JSON.parse(await readBoundedResponseBody(response, this.config.plane, limit)) as T;
        }
        const apiError = await this.decodeError(response);
        if (attempt < maxAttempts && RETRYABLE_STATUS.has(response.status)) {
          const retryAfterMs = response.status === 429 || response.status === 503 ? apiError.retryAfterMs : undefined;
          await abortableDelay(retryAfterMs ?? jitter(attempt, retry.maxDelayMs), call.signal);
          continue;
        }
        throw apiError;
      } finally {
        lifetime.clear();
      }
    }
    throw new Error(`PostGrip ${this.config.plane} request attempts exhausted`);
  }

  private async decodeError(response: Response): Promise<PostGripAPIError> {
    let value: Record<string, unknown> = {};
    try {
      const decoded: unknown = JSON.parse(await readBoundedResponseBody(response, this.config.plane, this.config.maxResponseBytes));
      if (typeof decoded === 'object' && decoded !== null && !Array.isArray(decoded)) {
        value = decoded as Record<string, unknown>;
      }
    } catch {
      // The typed fallback intentionally excludes the upstream response body.
    }
    return this.config.createError(
      response.status,
      typeof value.code === 'string' ? value.code : 'HTTP_ERROR',
      typeof value.message === 'string' ? value.message : response.statusText,
      typeof value.requestId === 'string' ? value.requestId : response.headers.get('x-request-id') ?? '',
      typeof value.details === 'object' && value.details !== null ? value.details as Record<string, unknown> : undefined,
      parseRetryAfter(response.headers.get('retry-after'), this.config.retry.retryAfterMaxDelayMs),
    );
  }
}

/** Rejects an idempotency key that is missing or not 1 to 128 visible ASCII characters. */
export function validateIdempotencyKey(key: string | undefined): void {
  if (key === undefined || !/^[!-~]{1,128}$/.test(key)) {
    throw new Error('idempotencyKey must contain 1 to 128 visible ASCII characters');
  }
}

/** Validates a configured exchange timeout, defaulting to 30 seconds. */
export function configuredTimeoutMs(plane: string, value: number | undefined): number {
  const timeoutMs = value ?? DEFAULT_TIMEOUT_MS;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error(`PostGrip ${plane} timeoutMs must be a positive number of milliseconds`);
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
