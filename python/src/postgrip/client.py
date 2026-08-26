from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._internal.config import resolve_config, validate_base_url
from .agent import Client as AgentClient
from .agent import Connection
from .service import AsyncServiceClient, ServiceClient
from .worker import AsyncWorkerClient, WorkerClient


class PostGrip:
    """Unified synchronous facade for Agent, Worker, and Service APIs."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        agent_url: str | None = None,
        worker_url: str | None = None,
        service_url: str | None = None,
        token: str | None = None,
        environ: Mapping[str, str] | None = None,
        insecure_development: bool = False,
        enable_retries: bool = False,
        timeout: float = 30.0,
    ) -> None:
        resolved = resolve_config(
            base_url=base_url,
            agent_url=agent_url,
            worker_url=worker_url,
            service_url=service_url,
            token=token,
            environ=environ,
        )
        validate_base_url("Agent", resolved.agent_url, insecure_development=insecure_development)
        common = {
            "insecure_development": insecure_development,
            "enable_retries": enable_retries,
            "timeout": timeout,
        }
        self.agent = AgentClient(Connection(resolved.agent_url, auth_token=resolved.token, timeout=timeout))
        self.workers = WorkerClient(base_url=resolved.worker_url, token=resolved.token, **common)
        self.services = ServiceClient(base_url=resolved.service_url, token=resolved.token, **common)

    @classmethod
    def from_env(cls, **options: Any) -> PostGrip:
        return cls(**options)


class AsyncPostGrip:
    """Unified async facade; management calls run in cancellation-aware threads."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        agent_url: str | None = None,
        worker_url: str | None = None,
        service_url: str | None = None,
        token: str | None = None,
        environ: Mapping[str, str] | None = None,
        insecure_development: bool = False,
        enable_retries: bool = False,
        timeout: float = 30.0,
    ) -> None:
        resolved = resolve_config(
            base_url=base_url,
            agent_url=agent_url,
            worker_url=worker_url,
            service_url=service_url,
            token=token,
            environ=environ,
        )
        validate_base_url("Agent", resolved.agent_url, insecure_development=insecure_development)
        common = {
            "insecure_development": insecure_development,
            "enable_retries": enable_retries,
            "timeout": timeout,
        }
        self.agent = AgentClient(Connection(resolved.agent_url, auth_token=resolved.token, timeout=timeout))
        self.workers = AsyncWorkerClient(base_url=resolved.worker_url, token=resolved.token, **common)
        self.services = AsyncServiceClient(base_url=resolved.service_url, token=resolved.token, **common)

    @classmethod
    def from_env(cls, **options: Any) -> AsyncPostGrip:
        return cls(**options)

    async def __aenter__(self) -> AsyncPostGrip:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None
