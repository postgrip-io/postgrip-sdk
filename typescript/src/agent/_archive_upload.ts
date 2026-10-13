import {
  resolveOpenAPIOperation,
  UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REPOSITORY,
  UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REVISION,
} from './generated/openapi.js';

/** The connection state the archive upload request needs. */
export interface ArchiveUploadTransport {
  readonly fetchImpl: typeof fetch;
  readonly baseUrl: string;
  readonly headers: HeadersInit | undefined;
  readonly authToken: string | undefined;
}

/**
 * Sends a raw gzipped tar archive to the workspace upload route on the
 * management lane and returns the unread response. The connection reads and
 * decodes it with its shared response bound and error handling.
 */
export function sendWorkspaceArchive(
  transport: ArchiveUploadTransport,
  archive: BodyInit,
  metadata: { repositoryName?: string; revision?: string },
): Promise<Response> {
  const headers = new Headers(transport.headers);
  headers.set('Content-Type', 'application/gzip');
  if (transport.authToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${transport.authToken}`);
  }
  if (metadata.repositoryName) headers.set(UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REPOSITORY, metadata.repositoryName);
  if (metadata.revision) headers.set(UPLOAD_WORKSPACE_HEADER_X_POST_GRIP_REVISION, metadata.revision);

  const operation = resolveOpenAPIOperation('uploadWorkspace');
  return transport.fetchImpl(`${transport.baseUrl}${operation.path}`, {
    method: operation.method,
    headers,
    body: archive,
    redirect: 'manual',
    // Node's fetch requires this for a streaming request body.
    ...(typeof archive === 'object' && archive !== null && Symbol.asyncIterator in (archive as object)
      ? { duplex: 'half' }
      : {}),
  } as RequestInit);
}
