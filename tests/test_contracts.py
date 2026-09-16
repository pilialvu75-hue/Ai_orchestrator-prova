import unittest

from airlab.contracts import BuildRequest


class BuildRequestTests(unittest.TestCase):
    def test_requires_task(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest.from_json({})

    def test_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest.from_json({"task": "build app", "mode": "magic"})

    def test_accepts_minimal_request(self) -> None:
        request = BuildRequest.from_json({"task": "build app"})
        self.assertEqual(request.mode, "plan")
        self.assertEqual(request.target, "web")
        self.assertEqual(request.task_family, "software")
        self.assertEqual(request.task_kind, "software.build")

    def test_accepts_cad_reconstruction_inputs_and_artifacts(self) -> None:
        request = BuildRequest.from_json(
            {
                "task": "Reconstruct this broken bracket",
                "task_family": "cad",
                "task_kind": "cad.reconstruct",
                "inputs": [
                    {"kind": "image", "reference": "attachment:front"},
                    {"kind": "measurement", "reference": "hole_spacing=63mm"},
                ],
                "requested_artifacts": ["STEP", "stl", "3mf"],
            }
        )
        self.assertEqual(request.task_family, "cad")
        self.assertEqual(request.task_kind, "cad.reconstruct")
        self.assertEqual(len(request.inputs), 2)
        self.assertEqual(request.requested_artifacts, ("step", "stl", "3mf"))

    def test_rejects_task_kind_from_another_family(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest(task="x", task_family="cad", task_kind="web.build")

    def test_gcode_requires_manufacturing_profile(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest(
                task="slice it",
                task_family="manufacturing",
                task_kind="manufacturing.slice",
                requested_artifacts=("gcode",),
            )

    def test_accepts_profile_bound_gcode_request(self) -> None:
        request = BuildRequest(
            task="slice it",
            task_family="manufacturing",
            task_kind="manufacturing.slice",
            requested_artifacts=("gcode",),
            context={"printer_profile": "printer:demo"},
        )
        self.assertEqual(request.requested_artifacts, ("gcode",))


if __name__ == "__main__":
    unittest.main()
