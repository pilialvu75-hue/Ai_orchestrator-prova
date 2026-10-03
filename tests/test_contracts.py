import unittest

from airlab.contracts import BuildRequest
from airlab.execution import ExecutionCorrelation


_REQUEST_FINGERPRINT = (
    "db5c57fcf1b8861cc7469c311cf073c96d0d377fa2291ac09656f450f2304b2c"
)


def _correlation() -> ExecutionCorrelation:
    return ExecutionCorrelation.create(
        project_id="project-abc",
        task_id="task-42",
        execution_id="execution-123",
        attempt_id="attempt-1",
        operation_id="software.build",
        request_fingerprint=_REQUEST_FINGERPRINT,
        checkpoint_id="checkpoint-1",
    )


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
        self.assertIsNone(request.execution_correlation)

    def test_accepts_optional_execution_correlation(self) -> None:
        correlation = _correlation()
        request = BuildRequest.from_json(
            {
                "task": "build app",
                "project_id": "project-abc",
                "execution_correlation": correlation.to_json(),
            }
        )

        self.assertEqual(request.execution_correlation, correlation)
        self.assertEqual(
            request.execution_correlation.idempotency_key,
            "airlab:v1:1637d6cf216f94593ac4e97bbb1bce0841553d46922a2ec754df8a8fe7eca701",
        )

    def test_rejects_tampered_execution_correlation(self) -> None:
        correlation = _correlation().to_json()
        correlation["idempotency_key"] = "airlab:v1:" + ("0" * 64)

        with self.assertRaises(ValueError):
            BuildRequest.from_json(
                {
                    "task": "build app",
                    "project_id": "project-abc",
                    "execution_correlation": correlation,
                }
            )

    def test_rejects_execution_correlation_project_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "project_id must match"):
            BuildRequest.from_json(
                {
                    "task": "build app",
                    "project_id": "project-other",
                    "execution_correlation": _correlation().to_json(),
                }
            )

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
