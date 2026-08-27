// Agent task-result signing.
//
// Mirrors the canonical-request layout in agent-sdk-protocol/signing.go:
//
//   agent-task-v1\n
//   {METHOD}\n
//   {PATH}\n
//   {QUERY}\n
//   {TIMESTAMP}\n
//   {BODY_SHA256_BASE64}\n
//
// The orchestrator verifies every signed POST against the agent's enrolled
// Ed25519 public key. Strict by default — signing is mandatory in production.

export {
  HEADER_AGENT_SIGNATURE,
  HEADER_AGENT_SIGNATURE_KEY_ID,
  HEADER_AGENT_SIGNATURE_TIMESTAMP,
} from './_signing_headers.js';

const AGENT_SIGNATURE_CONTEXT = 'agent-task-v1';
const NODE_CRYPTO_SPECIFIER = ['node', 'crypto'].join(':');

type NodeCrypto = typeof import('node:crypto');
type KeyObject = import('node:crypto').KeyObject;

let nodeCryptoPromise: Promise<NodeCrypto> | undefined;

function loadNodeCrypto(): Promise<NodeCrypto> {
  nodeCryptoPromise ??= import(NODE_CRYPTO_SPECIFIER) as Promise<NodeCrypto>;
  return nodeCryptoPromise;
}

export interface AgentSigningKey {
  privateKey: KeyObject;
  publicKey: KeyObject;
  publicKeyBase64: string;
  keyId: string;
}

export async function importSigningKeyFromBase64(encoded: string): Promise<AgentSigningKey> {
  const { createHash, createPrivateKey, createPublicKey } = await loadNodeCrypto();
  const raw = decodeBase64(encoded);
  if (raw.length !== 32 && raw.length !== 64) {
    throw new Error(`Ed25519 private key has ${raw.length} bytes, want 32 or 64`);
  }
  const seed = raw.subarray(0, 32);
  const privateKey = createPrivateKey({
    key: concatenateBytes(
      decodeHex('302e020100300506032b657004220420'),
      seed,
    ) as unknown as import('node:buffer').Buffer,
    format: 'der',
    type: 'pkcs8',
  });
  const publicKey = createPublicKey(privateKey);
  const jwk = publicKey.export({ format: 'jwk' });
  if (typeof jwk.x !== 'string') {
    throw new Error('Ed25519 public key export missing x');
  }
  const rawPub = decodeBase64(jwk.x, true);
  const publicKeyBase64 = encodeBase64(rawPub);
  const keyId = createHash('sha256').update(rawPub).digest('hex').slice(0, 16);
  return { privateKey, publicKey, publicKeyBase64, keyId };
}

export async function canonicalRequest(method: string, path: string, query: string, timestampUnix: number, body: Uint8Array): Promise<Uint8Array> {
  const { createHash } = await loadNodeCrypto();
  const bodyDigest = createHash('sha256').update(body).digest('base64');
  return new TextEncoder().encode([
    AGENT_SIGNATURE_CONTEXT,
    method.toUpperCase(),
    path,
    query,
    String(timestampUnix),
    bodyDigest,
    '',
  ].join('\n'));
}

export async function signRequest(privateKey: KeyObject, method: string, path: string, query: string, timestampUnix: number, body: Uint8Array): Promise<string> {
  const { sign } = await loadNodeCrypto();
  const canonical = await canonicalRequest(method, path, query, timestampUnix, body);
  return encodeBase64(sign(null, canonical, privateKey));
}

function decodeBase64(value: string, urlSafe = false): Uint8Array {
  const normalized = urlSafe
    ? value.replace(/-/g, '+').replace(/_/g, '/')
    : value;
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
  const decoded = atob(padded);
  return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
}

function encodeBase64(value: Uint8Array): string {
  let binary = '';
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function decodeHex(value: string): Uint8Array {
  if (value.length % 2 !== 0) throw new Error('hex input must contain complete bytes');
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(value.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

function concatenateBytes(left: Uint8Array, right: Uint8Array): Uint8Array {
  const combined = new Uint8Array(left.length + right.length);
  combined.set(left);
  combined.set(right, left.length);
  return combined;
}
