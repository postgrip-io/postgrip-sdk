import {
  CONNECT_SANDBOX_SESSION_PATH_SESSION_ID,
  CONNECT_SANDBOX_SESSION_QUERY_TICKET,
  resolveOpenAPIOperation,
} from './generated/openapi.js';

/**
 * Bound on a single frame through the session relay, in either direction. A
 * peer writing more has its session closed rather than forwarded, so chunk
 * writes at or below this.
 */
export const SANDBOX_RELAY_MAX_FRAME_BYTES = 1 << 20;

/**
 * Exec exit codes arrive as the WebSocket close status, `4000 + code`. A close
 * outside this range is a transport failure, not a process exit.
 */
export const SANDBOX_EXEC_CLOSE_STATUS_BASE = 4000;
export const SANDBOX_EXEC_CLOSE_STATUS_MAX = SANDBOX_EXEC_CLOSE_STATUS_BASE + 255;

/** Decodes a process exit code from a WebSocket close status. */
export function sandboxExecExitCode(closeStatus: number): number | undefined {
  if (closeStatus < SANDBOX_EXEC_CLOSE_STATUS_BASE || closeStatus > SANDBOX_EXEC_CLOSE_STATUS_MAX) {
    return undefined;
  }
  return closeStatus - SANDBOX_EXEC_CLOSE_STATUS_BASE;
}

export function sandboxInputBytes(data: Uint8Array | string): Uint8Array {
  const bytes = typeof data === 'string' ? new TextEncoder().encode(data) : data;
  if (bytes.byteLength > SANDBOX_RELAY_MAX_FRAME_BYTES) {
    throw new Error(
      `postgrip-agent: sandbox write of ${bytes.byteLength} bytes exceeds the relay frame limit ` +
        `(${SANDBOX_RELAY_MAX_FRAME_BYTES}); chunk your writes`,
    );
  }
  return bytes;
}

/** Builds the ws(s):// relay URL from an http(s) API base URL. */
export function sandboxRelayUrl(
  baseUrl: string,
  sessionId: string,
  ticket: string,
  insecureDevelopment = false,
): string {
  const base = baseUrl.trim().replace(/\/+$/, '');
  const separator = base.indexOf('://');
  const scheme = separator === -1 ? '' : base.slice(0, separator).toLowerCase();
  const remainder = separator === -1 ? '' : base.slice(separator + 3);
  let origin: string;
  if (scheme === 'https') origin = `wss://${remainder}`;
  else if (scheme === 'wss') origin = `wss://${remainder}`;
  else if (scheme === 'http' || scheme === 'ws') {
    if (!insecureDevelopment) {
      throw new Error('postgrip-agent: sandbox relay base must use WSS unless insecureDevelopment is enabled');
    }
    origin = `ws://${remainder}`;
  }
  else throw new Error(`postgrip-agent: sandbox relay base must be http(s) or ws(s): ${baseUrl}`);
  const operation = resolveOpenAPIOperation(
    'connectSandboxSession',
    { [CONNECT_SANDBOX_SESSION_PATH_SESSION_ID]: sessionId },
    new URLSearchParams({ [CONNECT_SANDBOX_SESSION_QUERY_TICKET]: ticket }),
  );
  return `${origin}${operation.path}`;
}
