from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from postgrip.agent import Connection
from postgrip.agent._connection import DEFAULT_ADDRESS

_ADDRESS_VARIABLES = (
    "POSTGRIP_AGENT_MANAGED_RUNTIME",
    "POSTGRIP_AGENTORCHESTRATOR_URL",
    "POSTGRIP_AGENT_URL",
    "POSTGRIP_URL",
)


class ConnectionAddressTest(unittest.TestCase):
    """A host agent launches a workflow.runtime task with its orchestrator's URL
    in POSTGRIP_AGENTORCHESTRATOR_URL and forbids the task from overriding
    POSTGRIP_* variables, so a managed runtime must prefer that URL over the
    general ones."""

    CASES = (
        (
            "managed runtime with only the host-injected address",
            None,
            {
                "POSTGRIP_AGENT_MANAGED_RUNTIME": "true",
                "POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test",
            },
            "https://orchestrator.example.test",
        ),
        (
            "managed runtime prefers the host-injected address",
            None,
            {
                "POSTGRIP_AGENT_MANAGED_RUNTIME": "true",
                "POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test",
                "POSTGRIP_AGENT_URL": "https://agent.example.test",
                "POSTGRIP_URL": "https://common.example.test",
            },
            "https://orchestrator.example.test",
        ),
        (
            "explicit address wins in a managed runtime",
            "https://explicit.example.test",
            {
                "POSTGRIP_AGENT_MANAGED_RUNTIME": "true",
                "POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test",
            },
            "https://explicit.example.test",
        ),
        (
            "managed runtime without a host-injected address",
            None,
            {
                "POSTGRIP_AGENT_MANAGED_RUNTIME": "true",
                "POSTGRIP_AGENT_URL": "https://agent.example.test",
            },
            "https://agent.example.test",
        ),
        (
            "orchestrator address is ignored outside a managed runtime",
            None,
            {
                "POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test",
                "POSTGRIP_AGENT_URL": "https://agent.example.test",
                "POSTGRIP_URL": "https://common.example.test",
            },
            "https://agent.example.test",
        ),
        (
            "common address follows the Agent address",
            None,
            {
                "POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test",
                "POSTGRIP_URL": "https://common.example.test",
            },
            "https://common.example.test",
        ),
        (
            "built-in cloud address is the last resort",
            None,
            {"POSTGRIP_AGENTORCHESTRATOR_URL": "https://orchestrator.example.test"},
            DEFAULT_ADDRESS,
        ),
    )

    def test_resolves_address_from_environment(self) -> None:
        for name, explicit, env, want in self.CASES:
            with self.subTest(name), patch.dict(os.environ, env):
                for variable in _ADDRESS_VARIABLES:
                    if variable not in env:
                        os.environ.pop(variable, None)
                self.assertEqual(Connection(explicit).address, want)


if __name__ == "__main__":
    unittest.main()
