import { httpStatusText } from '../internal/http.js';
import { PostGripAPIError, type APIErrorFields } from '../internal/transport.js';

export class PostGripAgentError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'PostGripAgentError';
  }
}

export class ApplicationFailure extends PostGripAgentError {
  readonly type: string;
  readonly nonRetryable: boolean;
  readonly details: unknown[];

  private constructor(message: string, options: {
    type?: string;
    nonRetryable?: boolean;
    details?: unknown[];
    cause?: unknown;
  } = {}) {
    super(message, { cause: options.cause });
    this.name = 'ApplicationFailure';
    this.type = options.type ?? 'ApplicationFailure';
    this.nonRetryable = options.nonRetryable ?? false;
    this.details = options.details ?? [];
  }

  static create(options: {
    message: string;
    type?: string;
    nonRetryable?: boolean;
    details?: unknown[];
    cause?: unknown;
  }): ApplicationFailure {
    return new ApplicationFailure(options.message, options);
  }

  static nonRetryable(message: string, type = 'NonRetryableFailure', ...details: unknown[]): ApplicationFailure {
    return new ApplicationFailure(message, { type, nonRetryable: true, details });
  }
}

export class TimeoutFailure extends PostGripAgentError {
  constructor(message = 'operation timed out') {
    super(message);
    this.name = 'TimeoutFailure';
  }
}

export class CancelledFailure extends PostGripAgentError {
  constructor(message = 'operation cancelled') {
    super(message);
    this.name = 'CancelledFailure';
  }
}

export class TaskFailedError extends PostGripAgentError {
  readonly taskId: string;

  constructor(taskId: string, message: string) {
    super(message);
    this.name = 'TaskFailedError';
    this.taskId = taskId;
  }
}

/**
 * A failed Agent HTTP exchange. Its text names only the method, route and
 * status, never server content; the envelope fields and the raw body are
 * available for explicit inspection.
 */
export class AgentAPIError extends PostGripAPIError {
  readonly method: string;
  readonly route: string;
  /** Untrusted server content that can contain secrets. Redact it before logging; the error text never includes it. */
  readonly responseBody: string;

  constructor(fields: APIErrorFields) {
    super(
      fields.status,
      fields.code,
      `postgrip-agent: ${JSON.stringify(fields.method)} ${JSON.stringify(fields.route)} -> ${fields.status} ${httpStatusText(fields.status)}`.trimEnd(),
      fields.requestId,
      fields.details,
      fields.retryAfterMs,
    );
    this.name = 'AgentAPIError';
    this.method = fields.method;
    this.route = fields.route;
    this.responseBody = fields.responseBody;
  }
}

/**
 * Whether a task mutation failed because the task is already terminal or no
 * longer leased by this agent. The server reports both as a 409 whose envelope
 * message names the condition.
 */
export function isTerminalTaskMutation(error: unknown): boolean {
  const message = error instanceof AgentAPIError
    ? (error.status === 409 ? envelopeMessage(error.responseBody) : '')
    : error instanceof Error ? error.message : String(error);
  return message.includes('terminal') || message.includes('not leased');
}

function envelopeMessage(body: string): string {
  try {
    const value: unknown = JSON.parse(body);
    if (typeof value === 'object' && value !== null) {
      const { message, error } = value as Record<string, unknown>;
      if (typeof message === 'string') return message;
      if (typeof error === 'string') return error;
    }
  } catch {
    // Not an envelope; no terminal condition is reported.
  }
  return '';
}

export function ignoreTerminalTaskMutation(error: unknown): void {
  if (!isTerminalTaskMutation(error)) throw error;
}
