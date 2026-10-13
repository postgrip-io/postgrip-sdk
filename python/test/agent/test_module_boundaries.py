from __future__ import annotations

import ast
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[2] / "src" / "postgrip" / "agent"


def _imported_modules(path: Path) -> set[str]:
    """Every module a source file imports, including under ``TYPE_CHECKING``."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            modules.add(prefix)
            if node.module is None:
                modules.update("." * node.level + alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


class AgentModuleBoundariesTest(unittest.TestCase):
    """The sandbox adapter must not depend on the client orchestration module.

    Importing a submodule always runs ``postgrip.agent.__init__``, which imports
    ``client``, so only a static check can prove the source cycle is gone.
    """

    def test_sandbox_does_not_import_client(self) -> None:
        for module in ("sandbox.py", "_sandbox_models.py", "_sandbox_transport.py"):
            imported = _imported_modules(AGENT / module)
            self.assertFalse(imported & {".client", "postgrip.agent.client"}, (module, imported))

    def test_sandbox_models_and_transport_do_not_import_orchestration(self) -> None:
        for module in ("_sandbox_models.py", "_sandbox_transport.py"):
            imported = _imported_modules(AGENT / module)
            self.assertFalse(imported & {".sandbox", "postgrip.agent.sandbox"}, (module, imported))
        self.assertFalse(_imported_modules(AGENT / "_sandbox_models.py") & {"._sandbox_transport", "urllib.request"})

    def test_connection_adapter_does_not_import_client_or_sandbox(self) -> None:
        imported = _imported_modules(AGENT / "_connection.py")
        self.assertFalse(
            imported & {".client", "postgrip.agent.client", ".sandbox", "postgrip.agent.sandbox"}, imported
        )

    def test_client_imports_sandbox_at_module_top(self) -> None:
        tree = ast.parse((AGENT / "client.py").read_text(encoding="utf-8"))
        top_level = {
            node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 1
        }
        self.assertIn("sandbox", top_level)

    def test_workflow_models_are_pure(self) -> None:
        imported = _imported_modules(AGENT / "_workflow_models.py")
        forbidden = {
            ".client", "._connection", ".sandbox", "postgrip.agent.client",
            "urllib.request", "asyncio", ".._internal.http",
        }
        self.assertFalse(imported & forbidden, imported)

    def test_history_walker_has_no_transport_or_client_dependency(self) -> None:
        imported = _imported_modules(AGENT / "_history.py")
        self.assertEqual(imported - {"__future__", "collections.abc", "typing", ".types"}, set(), imported)
        connection = (AGENT / "_connection.py").read_text(encoding="utf-8")
        self.assertNotIn("def _iter_history_pages", connection)
        self.assertIn("_history.iter_task_events(self, task_id)", connection)
        self.assertIn("_history.iter_workflow_history(self, workflow_id_or_run_id)", connection)

    def test_client_keeps_every_name_it_previously_provided(self) -> None:
        from postgrip.agent import client

        for name in (
            "Client", "WorkflowClient", "WorkflowHandle", "WorkflowUpdateHandle", "TaskClient", "ScheduleClient",
            "Connection", "DEFAULT_ADDRESS", "has_authorization_header", "urlopen", "run_cancellable",
            "_workflow_query_options",
        ):
            self.assertTrue(hasattr(client, name), name)


if __name__ == "__main__":
    unittest.main()
