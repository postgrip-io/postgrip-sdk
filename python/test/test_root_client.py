from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from _http_fakes import FakeOpener, FakeResponse
from postgrip import AsyncPostGrip, PostGrip


class RootClientTests(unittest.TestCase):
    def test_one_token_authenticates_all_three_planes(self) -> None:
        client = PostGrip(
            base_url="https://api.example.test",
            token="opaque-one-token",
        )
        agent_requests = []
        management_requests = []

        def agent_urlopen(request: object, timeout: float = 0) -> FakeResponse:
            agent_requests.append(request)
            return FakeResponse([])

        def management_open(request: object, timeout: float = 0) -> FakeResponse:
            management_requests.append(request)
            if "/services" in request.full_url:
                return FakeResponse({"items": [], "nextCursor": ""})
            return FakeResponse({"items": []})

        client.workers._opener.open = management_open
        client.services._opener.open = management_open

        with patch("postgrip.agent.client.urlopen", agent_urlopen):
            client.agent.connection.list_workflows()
        client.workers.list()
        client.services.list()

        requests = agent_requests + management_requests
        self.assertEqual(
            [request.get_header("Authorization") for request in requests],
            ["Bearer opaque-one-token"] * 3,
        )

    def test_environment_precedence(self) -> None:
        client = PostGrip.from_env(
            agent_url="https://explicit-agent.example.test",
            environ={
                "POSTGRIP_URL": "https://common.example.test",
                "POSTGRIP_AGENT_URL": "https://ignored-agent.example.test",
                "POSTGRIP_WORKER_URL": "https://worker.example.test",
                "POSTGRIP_TOKEN": "pgt_environment",
            },
        )
        self.assertEqual(client.agent.connection.address, "https://explicit-agent.example.test")
        self.assertEqual(client.workers._base_url, "https://worker.example.test/")
        self.assertEqual(client.services._base_url, "https://common.example.test/")

    def test_async_context_exposes_all_planes(self) -> None:
        async def check() -> None:
            async with AsyncPostGrip(
                base_url="https://api.example.test",
                token="pgt_async",
            ) as client:
                self.assertEqual(client.agent.connection.auth_token, "pgt_async")
                self.assertEqual(client.workers._sync._token, "pgt_async")
                self.assertEqual(client.services._sync._token, "pgt_async")

        asyncio.run(check())

    def test_management_subpaths_do_not_import_agent_or_sandbox_modules(self) -> None:
        source = (
            "import sys; import postgrip.worker; import postgrip.service; "
            "assert 'postgrip.agent' not in sys.modules; "
            "assert 'websockets' not in sys.modules"
        )
        environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        result = subprocess.run([sys.executable, "-c", source], env=environment, check=False)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
