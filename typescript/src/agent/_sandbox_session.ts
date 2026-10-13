import { sandboxExecExitCode, sandboxInputBytes } from './_sandbox_relay.js';

export interface SandboxWebSocketConnectOptions {
  /** Connection-level headers, including the management Authorization header. */
  readonly headers: Readonly<Record<string, string>>;
}

/** Creates an authenticated WebSocket for a sandbox relay connection. */
export type SandboxWebSocketFactory = (
  url: string,
  options: SandboxWebSocketConnectOptions,
) => WebSocket;

export interface SandboxSessionOptions {
  command?: string[];
  /**
   * PTY size, defaulting to 24x80. Fixed for the session's life — the relay
   * has no resize channel, so a terminal resized mid-session cannot tell the
   * sandbox.
   */
  rows?: number;
  columns?: number;
  /**
   * Overrides where the WebSocket dials, defaulting to the connection's base
   * URL. Needed when the API is reached through a proxy that doesn't forward
   * WebSocket upgrades — the relay is deliberately not proxied.
   */
  relayBaseUrl?: string;
  /**
   * Overrides WebSocket construction. The factory receives every configured
   * connection header, including the management Authorization credential.
   */
  webSocketFactory?: SandboxWebSocketFactory;
  /**
   * Legacy constructor override. Header-capable Node implementations receive
   * the connection headers in their constructor options. Prefer
   * `webSocketFactory` for new integrations.
   */
  webSocketImpl?: typeof WebSocket;
}

/**
 * A live sandbox session: a raw bidirectional byte stream plus the process
 * exit code once it closes.
 *
 * For `pty` this is terminal traffic; for `exec` it is the process's stdout
 * and stderr **interleaved on one stream** — the relay multiplexes both, so
 * they cannot be separated client-side. Message boundaries are otherwise
 * opaque, except that `closeInput` sends the reserved zero-length binary
 * stdin-EOF message.
 */
export class SandboxSession {
  private readonly closed: Promise<number | undefined>;
  private inputClosed = false;
  private reportedExitCode: number | undefined;

  constructor(private readonly socket: WebSocket) {
    this.closed = new Promise((resolve) => {
      socket.addEventListener('close', (event) => {
        this.reportedExitCode = sandboxExecExitCode(event.code);
        resolve(this.reportedExitCode);
      }, { once: true });
    });
  }

  /** Sends bytes to the sandbox's stdin. */
  send(data: Uint8Array | string): void {
    if (this.inputClosed) {
      throw new Error('postgrip-agent: sandbox session input is closed');
    }
    const bytes = sandboxInputBytes(data);
    // An empty binary message is the stdin-EOF control. Preserve send's byte
    // stream semantics by making empty writes no-ops; closeInput owns it.
    if (bytes.byteLength === 0) return;
    this.socket.send(bytes);
  }

  /** Signals stdin EOF while keeping output and exit-status delivery open. */
  closeInput(): void {
    if (this.inputClosed) return;
    try {
      this.socket.send(new Uint8Array(0));
    } catch (error) {
      // A command that does not read stdin may report its valid exit before
      // this empty EOF frame is written. Preserve that process result; a
      // transport close without an exec status must still surface as error.
      if (this.reportedExitCode === undefined) throw error;
    }
    this.inputClosed = true;
  }

  /** Registers a handler for sandbox output. */
  onData(handler: (chunk: Uint8Array) => void): void {
    this.socket.addEventListener('message', (event: MessageEvent) => {
      const data = event.data;
      if (data instanceof ArrayBuffer) handler(new Uint8Array(data));
      else if (data instanceof Uint8Array) handler(data);
      else if (typeof data === 'string') handler(new TextEncoder().encode(data));
    });
  }

  /**
   * Resolves with the process exit code when the session ends.
   *
   * Resolves `undefined` when the close status carried no exit code — which
   * means the transport ended rather than the process, and must not be read as
   * a successful run.
   */
  async exitCode(): Promise<number | undefined> {
    return this.closed;
  }

  /** Closes the session immediately. */
  close(): void {
    this.socket.close();
  }
}

/**
 * Dials the relay and resolves with the session once the socket opens. The
 * caller supplies an authorized relay URL and the connection headers.
 */
export async function openSandboxSession(
  createWebSocket: SandboxWebSocketFactory,
  url: string,
  options: SandboxWebSocketConnectOptions,
): Promise<SandboxSession> {
  const socket = createWebSocket(url, options);
  socket.binaryType = 'arraybuffer';
  await new Promise<void>((resolve, reject) => {
    socket.addEventListener('open', () => resolve(), { once: true });
    socket.addEventListener('error', () => reject(new Error('postgrip-agent: sandbox relay dial failed')), {
      once: true,
    });
  });
  return new SandboxSession(socket);
}

type HeaderCapableWebSocketConstructor = new (
  url: string,
  protocols?: string | string[],
  options?: { headers?: Readonly<Record<string, string>> },
) => WebSocket;

export async function resolveSandboxWebSocketFactory(
  options: SandboxSessionOptions,
  headers: Readonly<Record<string, string>>,
): Promise<SandboxWebSocketFactory> {
  if (options.webSocketFactory) {
    return options.webSocketFactory;
  }
  if (options.webSocketImpl) {
    const WebSocketImpl = options.webSocketImpl as unknown as HeaderCapableWebSocketConstructor;
    return (url, connectOptions) => new WebSocketImpl(url, [], { headers: connectOptions.headers });
  }

  // The standard WebSocket API cannot attach an Authorization header. Use the
  // header-capable `ws` implementation on Node/Bun even when a global
  // WebSocket exists (Node 22+), otherwise token-authenticated relays fail.
  if (typeof process !== 'undefined' && process.versions?.node) {
    const { WebSocket: NodeWebSocket } = await import('ws');
    return (url, connectOptions) => new NodeWebSocket(url, {
      headers: { ...connectOptions.headers },
    }) as unknown as WebSocket;
  }

  const WebSocketImpl = globalThis.WebSocket;
  if (!WebSocketImpl) {
    throw new Error(
      'postgrip-agent: no WebSocket implementation available; pass webSocketFactory',
    );
  }
  if (Object.keys(headers).length > 0) {
    throw new Error(
      'postgrip-agent: browser WebSocket cannot send configured relay headers; ' +
        'authenticate with same-origin cookies or pass webSocketFactory in a header-capable runtime',
    );
  }
  return (url) => new WebSocketImpl(url);
}
