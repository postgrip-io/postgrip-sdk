from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

_MAX_RESPONSE_BYTES = 4 << 20


class SafeRedirectHandler(HTTPRedirectHandler):
    """Follow same-origin redirects but refuse cross-origin redirects."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        target = urljoin(req.full_url, newurl)
        if _origin(req.full_url) != _origin(target):
            return None
        return super().redirect_request(req, fp, code, msg, headers, target)


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80 if parsed.scheme.lower() == "http" else None
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


_REDIRECT_SAFE_OPENER: OpenerDirector = build_opener(SafeRedirectHandler())


def redirect_safe_open(request: Request, timeout: float | None = None) -> Any:
    """Open one request without following a redirect to another origin."""

    return _REDIRECT_SAFE_OPENER.open(request, timeout=timeout)


def read_bounded_response(source: Any, plane: str, *, bounded: bool = True) -> bytes:
    """Read a response with the generic bound or an explicit contract exception."""

    if not bounded:
        return source.read()
    chunks: list[bytes] = []
    remaining = _MAX_RESPONSE_BYTES + 1
    while remaining > 0:
        chunk = source.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError(f"PostGrip {plane} response is invalid or too large")
    return body
