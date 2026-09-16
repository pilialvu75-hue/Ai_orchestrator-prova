import unittest

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import MemoryDiagnostics, NullModuleLibrary, NullResearcher
from airlab.contracts import BuildRequest
from airlab.service import BuilderService


class BuilderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diagnostics = MemoryDiagnostics()
        self.service = BuilderService(
            engine=MockBuilderEngine(),
            library=NullModuleLibrary(),
            researcher=NullResearcher(),
            diagnostics=self.diagnostics,
        )

    def test_plan_is_hardware_independent(self) -> None:
        response = self.service.execute(BuildRequest(task="Create a notes app"))
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.engine_id, "mock-builder-v1")
        self.assertEqual(response.operations, [])
        self.assertTrue(response.metadata["mock"])

    def test_implement_produces_deterministic_mock_operation(self) -> None:
        response = self.service.execute(
            BuildRequest(task="Create a notes app", mode="implement")
        )
        self.assertEqual(len(response.operations), 1)
        self.assertEqual(response.operations[0].action, "create")
        self.assertEqual(response.operations[0].path, ".airlab/mock-result.txt")

    def test_diagnostics_never_receive_task_text(self) -> None:
        secret_task = "private user project text"
        self.service.execute(BuildRequest(task=secret_task))
        serialized = repr(self.diagnostics.events)
        self.assertNotIn(secret_task, serialized)
        self.assertEqual([e[0] for e in self.diagnostics.events], ["build_started", "build_finished"])


if __name__ == "__main__":
    unittest.main()
