from __future__ import annotations

import json
import threading
import unittest
from urllib.request import Request, urlopen

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import MemoryDiagnostics, NullModuleLibrary, NullResearcher
from airlab.http_api import create_server
from airlab.service import BuilderService


class AirLabHttpRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diagnostics = MemoryDiagnostics()
        service = BuilderService(
            engine=MockBuilderEngine(),
            library=NullModuleLibrary(),
            researcher=NullResearcher(),
            diagnostics=self.diagnostics,
        )
        self.server = create_server(
            service,
            host="127.0.0.1",
            port=0,
            auth_token=None,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _get_json(self, path: str) -> dict[str, object]:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def test_health_capabilities_and_cad_task_use_real_http(self) -> None:
        health = self._get_json("/health")
        self.assertEqual(health["service"], "airlab")
        self.assertEqual(health["engine_id"], "mock-builder-v2")

        capabilities = self._get_json("/v1/capabilities")
        self.assertIn("cad", capabilities["task_families"])
        self.assertIn("image", capabilities["input_kinds"])
        self.assertIn("stl", capabilities["artifact_formats"])

        private_task_text = "Reconstruct my private broken bracket"
        result = self._post_json(
            "/v1/tasks",
            {
                "task": private_task_text,
                "project_id": "project-3d-1",
                "target": "3d-print",
                "mode": "plan",
                "task_family": "cad",
                "task_kind": "cad.reconstruct",
                "inputs": [
                    {
                        "kind": "image",
                        "reference": "attachment:front",
                    },
                    {
                        "kind": "measurement",
                        "reference": "hole_spacing=63mm",
                    },
                ],
                "requested_artifacts": ["step", "stl", "3mf"],
            },
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["engine_id"], "mock-builder-v2")
        self.assertIn(
            "preserve a parametric/editable master before derived print files",
            result["plan"],
        )

        artifacts = result["artifacts"]
        self.assertEqual(artifacts[0]["format"], "airlab")
        self.assertTrue(artifacts[0]["editable"])
        self.assertFalse(artifacts[0]["derived"])
        self.assertEqual(
            [artifact["format"] for artifact in artifacts[1:]],
            ["step", "stl", "3mf"],
        )

        serialized_diagnostics = repr(self.diagnostics.events)
        self.assertNotIn(private_task_text, serialized_diagnostics)

    def test_manufacturing_gcode_requires_printer_profile(self) -> None:
        payload = {
            "task": "Slice this model",
            "project_id": "project-3d-2",
            "target": "3d-print",
            "mode": "implement",
            "task_family": "manufacturing",
            "task_kind": "manufacturing.slice",
            "requested_artifacts": ["gcode"],
            "context": {
                "printer_profile": {
                    "id": "printer-profile-1",
                    "nozzle_mm": 0.4,
                }
            },
        }

        result = self._post_json("/v1/tasks", payload)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["artifacts"][0]["format"], "gcode")
        self.assertEqual(result["artifacts"][0]["role"], "machine")


if __name__ == "__main__":
    unittest.main()
