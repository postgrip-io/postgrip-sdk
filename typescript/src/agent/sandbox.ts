import type { Connection } from './connection.js';
import {
  SANDBOX_EXEC_CLOSE_STATUS_BASE,
  SANDBOX_EXEC_CLOSE_STATUS_MAX,
  SANDBOX_RELAY_MAX_FRAME_BYTES,
  sandboxExecExitCode,
  sandboxInputBytes,
  sandboxRelayUrl,
} from './_sandbox_relay.js';
import {
  resolveSandboxWebSocketFactory,
  SandboxSession,
  type SandboxSessionOptions,
  type SandboxWebSocketConnectOptions,
  type SandboxWebSocketFactory,
} from './_sandbox_session.js';
import type {
  CreateSandboxSessionRequest,
  CreateSandboxSessionResponse,
  Sandbox,
  SandboxCreateRequest,
  SandboxSessionKind,
  SandboxWorkspace,
} from './types.js';

export {
  SANDBOX_EXEC_CLOSE_STATUS_BASE,
  SANDBOX_EXEC_CLOSE_STATUS_MAX,
  SANDBOX_RELAY_MAX_FRAME_BYTES,
  sandboxExecExitCode,
  sandboxRelayUrl,
  SandboxSession,
};
export type { SandboxSessionOptions, SandboxWebSocketConnectOptions, SandboxWebSocketFactory };

export interface SandboxWaitOptions {
  /** Defaults to 120_000 ms. */
  timeoutMs?: number;
  /** Defaults to 1_000 ms. */
  pollIntervalMs?: number;
  signal?: AbortSignal;
}

export interface SandboxExecOptions extends Omit<SandboxSessionOptions, 'command'> {
  /** Bytes delivered to stdin before the SDK signals EOF. Defaults to empty. */
  stdin?: Uint8Array | string;
}

/**
 * Sandbox lifecycle and execution.
 *
 * Sandbox endpoints authenticate on the management lane: construct the
 * Connection with `authToken` set to a management token. An agent access token
 * is rejected by every endpoint here.
 */
export class SandboxClient {
  constructor(private readonly connection: Connection) {}

  async create(request: SandboxCreateRequest): Promise<Sandbox> {
    return this.connection.createSandbox(request);
  }

  async list(): Promise<Sandbox[]> {
    return this.connection.listSandboxes();
  }

  async get(sandboxId: string, signal?: AbortSignal): Promise<Sandbox> {
    return this.connection.getSandbox(requireSandboxId(sandboxId), signal);
  }

  async start(sandboxId: string): Promise<Sandbox> {
    return this.connection.startSandbox(requireSandboxId(sandboxId));
  }

  async stop(sandboxId: string): Promise<Sandbox> {
    return this.connection.stopSandbox(requireSandboxId(sandboxId));
  }

  async delete(sandboxId: string): Promise<Sandbox> {
    return this.connection.deleteSandbox(requireSandboxId(sandboxId));
  }

  async uploadWorkspace(
    archive: BodyInit,
    metadata: { repositoryName?: string; revision?: string } = {},
  ): Promise<SandboxWorkspace> {
    return this.connection.uploadWorkspace(archive, metadata);
  }

  async listWorkspaces(): Promise<SandboxWorkspace[]> {
    return this.connection.listWorkspaces();
  }

  async getWorkspace(workspaceId: string): Promise<SandboxWorkspace> {
    return this.connection.getWorkspace(requireWorkspaceId(workspaceId));
  }

  /** Deletes a workspace unless a live sandbox still references it. */
  async deleteWorkspace(workspaceId: string): Promise<void> {
    await this.connection.deleteWorkspace(requireWorkspaceId(workspaceId));
  }

  async createSession(
    sandboxId: string,
    request: CreateSandboxSessionRequest = {},
  ): Promise<CreateSandboxSessionResponse> {
    return this.connection.createSandboxSession(requireSandboxId(sandboxId), request);
  }

  /**
   * Polls until the sandbox is ready, fails, or the wait expires.
   *
   * Readiness is `observedState === 'running'` **and**
   * `observedGeneration >= generation`. State alone can predate a start or
   * stop the assigned agent hasn't observed yet, so checking only the state
   * can return a sandbox that is about to stop.
   */
  async waitUntilRunning(sandboxId: string, options: SandboxWaitOptions = {}): Promise<Sandbox> {
    const timeoutMs = options.timeoutMs ?? 120_000;
    const pollIntervalMs = options.pollIntervalMs ?? 1_000;
    const deadline = Date.now() + timeoutMs;
    let last: Sandbox | undefined;

    for (;;) {
      options.signal?.throwIfAborted();
      // Bound the request itself, not just the gaps between requests. Without
      // a signal a stalled management call stays pending forever, and the loop
      // never reaches the deadline check below — so waitUntilRunning could
      // outlive its own timeout indefinitely. The signal combines the caller's
      // with what remains of the deadline, so whichever comes first wins.
      const remaining = deadline - Date.now();
      const pollSignal = combineAbortSignals(options.signal, remaining > 0 ? remaining : 1);
      const record = await this.get(sandboxId, pollSignal);
      last = record;
      // Both readiness and failure are read at the current generation. A
      // `failed` left over from the previous generation does not describe the
      // state just requested, so treating it as terminal made a start issued
      // against a failed sandbox reject during the reconciliation window —
      // exactly when a caller is trying to recover.
      const observed = (record.observedGeneration ?? 0) >= (record.generation ?? 0);
      if (record.observedState === 'running' && observed) {
        return record;
      }
      if (record.observedState === 'failed' && observed) {
        throw new Error(
          `postgrip-agent: sandbox ${sandboxId} failed: ` +
            (record.failureMessage || record.failureCode || 'no failure detail reported'),
        );
      }
      if (Date.now() >= deadline) {
        throw new Error(
          `postgrip-agent: sandbox ${sandboxId} was not running within ${timeoutMs}ms ` +
            `(last observed state: ${last?.observedState ?? 'unknown'})`,
        );
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
  }

  /**
   * Creates a session and dials the relay.
   *
   * The sandbox must already be running; while it comes up the server rejects
   * session creation with a retryable 400, so call `waitUntilRunning` first.
   * The ticket is single-use and short-lived, which is why creating and
   * dialling are one call.
   */
  async openSession(
    sandboxId: string,
    kind: Exclude<SandboxSessionKind, 'port'>,
    options: SandboxSessionOptions = {},
  ): Promise<SandboxSession> {
    if (kind !== 'pty' && kind !== 'exec') {
      throw new Error("postgrip-agent: sandbox session kind must be 'pty' or 'exec'");
    }
    if (kind === 'exec' && (!options.command || options.command.length === 0)) {
      throw new Error('postgrip-agent: sandbox exec requires a command');
    }
    const relayHeaders: Record<string, string> = {};
    this.connection.managementHeaders().forEach((value, name) => {
      relayHeaders[name] = value;
    });
    Object.freeze(relayHeaders);
    // Resolve the transport before creating the single-use server session. A
    // missing implementation must not burn a ticket or start an exec command.
    const createWebSocket = await resolveSandboxWebSocketFactory(options, relayHeaders);
    const relayBaseUrl = options.relayBaseUrl ?? this.connection.baseUrl;
    sandboxRelayUrl(
      relayBaseUrl,
      'validation',
      'validation',
      this.connection.insecureDevelopment,
    );
    const session = await this.createSession(sandboxId, {
      kind,
      command: options.command,
      rows: options.rows,
      columns: options.columns,
    });
    const url = sandboxRelayUrl(
      relayBaseUrl,
      session.id!,
      session.ticket!,
      this.connection.insecureDevelopment,
    );
    // The ticket selects and authorizes the session; the management credential
    // separately authenticates the request. Both are required by the contract.
    const socket = createWebSocket(url, { headers: relayHeaders });
    socket.binaryType = 'arraybuffer';
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener('open', () => resolve(), { once: true });
      socket.addEventListener('error', () => reject(new Error('postgrip-agent: sandbox relay dial failed')), {
        once: true,
      });
    });
    return new SandboxSession(socket);
  }

  /**
   * Runs a command in the sandbox and resolves with its exit code and output.
   *
   * `output` carries stdout and stderr interleaved — the relay is one stream.
   */
  async exec(
    sandboxId: string,
    command: string[],
    options: SandboxExecOptions = {},
  ): Promise<{ exitCode: number | undefined; output: Uint8Array }> {
    const { stdin, ...sessionOptions } = options;
    // Validate deterministic local failures before createSession starts a
    // remote command and consumes its single-use relay ticket.
    const stdinBytes = stdin === undefined ? undefined : sandboxInputBytes(stdin);
    const session = await this.openSession(sandboxId, 'exec', { ...sessionOptions, command });
    const chunks: Uint8Array[] = [];
    session.onData((chunk) => chunks.push(chunk));
    try {
      if (stdinBytes !== undefined) session.send(stdinBytes);
      session.closeInput();
    } catch (error) {
      // A socket can fail after the remote exec has started. The caller has no
      // session handle from this convenience method, so tear it down here.
      try {
        session.close();
      } catch {
        // Preserve the stdin setup failure; close is best-effort cleanup.
      }
      throw error;
    }
    const exitCode = await session.exitCode();
    let total = 0;
    for (const c of chunks) total += c.byteLength;
    const output = new Uint8Array(total);
    let offset = 0;
    for (const c of chunks) {
      output.set(c, offset);
      offset += c.byteLength;
    }
    return { exitCode, output };
  }
}

function requireSandboxId(sandboxId: string): string {
  if (!sandboxId) {
    // Otherwise this builds /api/v1/sandboxes/ and hits the collection route.
    throw new Error('postgrip-agent: sandbox id is required');
  }
  return sandboxId;
}

function requireWorkspaceId(workspaceId: string): string {
  if (!workspaceId) {
    throw new Error('postgrip-agent: workspace id is required');
  }
  return workspaceId;
}

/**
 * A signal that aborts on the caller's signal or after `timeoutMs`, whichever
 * comes first.
 *
 * `AbortSignal.any` and `AbortSignal.timeout` are both Node 20+ / modern
 * browsers, which this package already targets, but they are guarded anyway:
 * on a runtime without them, falling back to the caller's signal alone leaves
 * the previous behaviour rather than throwing at an unrelated call site.
 */
function combineAbortSignals(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal | undefined {
  if (typeof AbortSignal?.timeout !== 'function') {
    return signal;
  }
  const deadlineSignal = AbortSignal.timeout(timeoutMs);
  if (!signal) {
    return deadlineSignal;
  }
  if (typeof AbortSignal.any !== 'function') {
    return signal;
  }
  return AbortSignal.any([signal, deadlineSignal]);
}
