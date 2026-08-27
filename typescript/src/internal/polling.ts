interface FollowPage<Entry> {
  readonly items: readonly Entry[];
  readonly nextCursor?: string;
}

interface FollowOptions<Entry, Page extends FollowPage<Entry>> {
  readonly cursor?: string;
  readonly signal?: AbortSignal;
  readonly emptyPageDelayMs: (page: Page) => number;
  readonly entryId?: (entry: Entry) => number;
}

export async function* followPages<Entry, Page extends FollowPage<Entry>>(
  fetchPage: (cursor: string | undefined) => Promise<Page>,
  options: FollowOptions<Entry, Page>,
): AsyncGenerator<Entry> {
  let cursor = options.cursor;
  let lastId: number | undefined;
  while (true) {
    options.signal?.throwIfAborted();
    const page = await fetchPage(cursor);
    cursor = page.nextCursor;
    for (const entry of page.items) {
      options.signal?.throwIfAborted();
      const entryId = options.entryId?.(entry);
      if (entryId === undefined || lastId === undefined || entryId > lastId) {
        if (entryId !== undefined) lastId = entryId;
        yield entry;
      }
    }
    if (page.items.length === 0) {
      await abortableDelay(options.emptyPageDelayMs(page), options.signal);
    }
  }
}

export function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const complete = () => {
      signal?.removeEventListener('abort', abort);
      resolve();
    };
    const timeout = setTimeout(complete, milliseconds);
    const abort = () => {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', abort);
      reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
    };
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, { once: true });
  });
}
