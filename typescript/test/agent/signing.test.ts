import { verify } from 'node:crypto';
import { describe, expect, it } from 'vitest';

import {
  canonicalRequest,
  importSigningKeyFromBase64,
  signRequest,
} from '../../src/agent/_signing.js';

describe('managed-runtime signing', () => {
  it('loads Node crypto lazily and preserves agent-task-v1 signatures', async () => {
    const privateSeed = Buffer.alloc(32, 7).toString('base64');
    const signingKey = await importSigningKeyFromBase64(privateSeed);
    const body = new TextEncoder().encode('{"result":"ok"}');
    const canonical = await canonicalRequest('POST', '/api/v1/agent/tasks/task-1/complete', 'agent_id=agent-1', 1_777_777_777, body);
    const signature = await signRequest(
      signingKey.privateKey,
      'POST',
      '/api/v1/agent/tasks/task-1/complete',
      'agent_id=agent-1',
      1_777_777_777,
      body,
    );

    expect(verify(null, canonical, signingKey.publicKey, Buffer.from(signature, 'base64'))).toBe(true);
  });
});
