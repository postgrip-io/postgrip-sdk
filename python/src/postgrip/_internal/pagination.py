from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from typing import Any, TypeVar

Page = TypeVar("Page", bound=Mapping[str, Any])


def iterate_pages(
    fetch: Callable[[str | None], Page],
    next_cursor_key: str,
    cursor: str | None = None,
) -> Iterator[Page]:
    while True:
        page = fetch(cursor)
        yield page
        cursor = page.get(next_cursor_key)
        if not cursor:
            return


async def iterate_pages_async(
    fetch: Callable[[str | None], Awaitable[Page]],
    next_cursor_key: str,
    cursor: str | None = None,
) -> AsyncIterator[Page]:
    while True:
        page = await fetch(cursor)
        yield page
        cursor = page.get(next_cursor_key)
        if not cursor:
            return
