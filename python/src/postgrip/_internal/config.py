from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class ResolvedConfig:
    agent_url: str
    worker_url: str
    service_url: str
    token: str


def validate_management_token(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("PostGrip management token is required")
    return token


def validate_idempotency_key(value: str) -> str:
    if re.fullmatch(r"[!-~]{1,128}", value) is None:
        raise ValueError("idempotency_key must contain 1 to 128 visible ASCII characters")
    return value


def validate_base_url(plane: str, value: str, *, insecure_development: bool = False) -> str:
    raw = value.strip()
    parsed = urlparse(raw)
    if not parsed.netloc or (
        parsed.scheme != "https" and not (insecure_development and parsed.scheme == "http")
    ):
        raise ValueError(f"PostGrip {plane} base_url must use HTTPS unless insecure_development is enabled")
    if "?" in raw or "#" in raw or parsed.query or parsed.fragment:
        raise ValueError(f"PostGrip {plane} base_url must not contain a query or fragment")
    return raw


def resolve_config(
    *,
    base_url: str | None = None,
    agent_url: str | None = None,
    worker_url: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConfig:
    values = os.environ if environ is None else environ
    common_url = _first(base_url, values.get("POSTGRIP_URL"))
    return ResolvedConfig(
        agent_url=_required_url("Agent", _first(agent_url, values.get("POSTGRIP_AGENT_URL"), common_url)),
        worker_url=_required_url("Worker", _first(worker_url, values.get("POSTGRIP_WORKER_URL"), common_url)),
        service_url=_required_url("Service", _first(service_url, values.get("POSTGRIP_SERVICE_URL"), common_url)),
        token=validate_management_token(_first(token, values.get("POSTGRIP_TOKEN")) or ""),
    )


def _first(*values: str | None) -> str | None:
    return next((value.strip() for value in values if value and value.strip()), None)


def _required_url(plane: str, value: str | None) -> str:
    if not value:
        raise ValueError(f"PostGrip {plane} URL is required; configure POSTGRIP_URL or POSTGRIP_{plane.upper()}_URL")
    return value
