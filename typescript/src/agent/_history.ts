const HISTORY_PAGE_MAXIMUM_LIMIT = 500;

export interface HistoryPageOptions {
  cursor?: string;
  limit?: number;
  signal?: AbortSignal;
}

export function historyPageQuery(options: HistoryPageOptions): URLSearchParams {
  const query = new URLSearchParams();
  if (options.cursor) query.set('cursor', options.cursor);
  if (options.limit != null) query.set('limit', String(options.limit));
  return query;
}

export async function* iterateHistoryPages<T>(
  fetchPage: (options: HistoryPageOptions) => Promise<{ items: T[]; nextCursor?: string }>,
  signal?: AbortSignal,
): AsyncGenerator<T, void, void> {
  let cursor: string | undefined;
  const seen = new Set<string>();
  while (true) {
    signal?.throwIfAborted();
    const page = await fetchPage({ cursor, limit: HISTORY_PAGE_MAXIMUM_LIMIT, signal });
    for (const item of page.items) {
      signal?.throwIfAborted();
      yield item;
    }
    if (page.nextCursor == null) return;
    const next = page.nextCursor.trim();
    if (next === '') throw new Error('postgrip-agent: history page returned an empty next cursor');
    if (seen.has(next)) throw new Error('postgrip-agent: history page repeated its next cursor');
    seen.add(next);
    cursor = next;
  }
}
