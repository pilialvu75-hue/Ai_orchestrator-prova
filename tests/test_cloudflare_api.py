from __future__ import annotations

import json
import unittest

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import (
    MemoryDiagnostics,
    NullModuleLibrary,
    NullResearcher,
)
from airlab.cloudflare_api import dispatch_cloudflare_request
from airlab.execution import ExecutionCorrelation
from airlab.service import BuilderService


TOKEN = "test-token"
AUTH = f"Bearer {TOKEN}"
FINGERPRINT = "db5c57fcf1b8861cc7469c311cf073c96d0d377fa2291ac09656f450f2304b2c"


def service() -> BuilderService:
    return BuilderService(
        engine=MockBuilderEngine(),
        library=NullModuleLibrary(),
        researcher=NullResearcher(),
        diagnostics=MemoryDiagnostics(),
    )


def execution_correlation() -> dict[str, object]:
    return ExecutionCorrelation.create(
        project_id="cloudflare-smoke",
        task_id="task-42",
        execution_id="execution-123",
        attempt_id="attempt-1",
        operation_id="software.build",
        request_fingerprint=FINGERPRINT,
        checkpoint_id="checkpoint-1",
    ).to_json()


class CloudflareApiTest(unittest.TestCase):
    def test_missing_worker_secret_fails_closed(self) -> None:
        result = dispatch_cloudflare_request(
            service(),
            method="GET",
            path="/health",
            authorization=None,
            body=None,
            auth_token=None,
        )

        self.assertEqual(result.status, 503)
        self.assertEqual(result.payload, {"error": "service_unconfigured"})

    def test_invalid_bearer_token_is_unauthorized(self) -> None:
        result = dispatch_cloudflare_request(
            service(),
            method="GET",
            path="/health",
            authorization="Bearer wrong",
            body=None,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 401)
        self.assertEqual(result.payload, {"error": "unauthorized"})

    def test_health_and_capabilities_match_airlab_contract(self) -> None:
        current = service()

        health = dispatch_cloudflare_request(
            current,
            method="GET",
            path="/health",
            authorization=AUTH,
            body=None,
            auth_token=TOKEN,
        )
        capabilities = dispatch_cloudflare_request(
            current,
            method="GET",
            path="/v1/capabilities",
            authorization=AUTH,
            body=None,
            auth_token=TOKEN,
        )

        self.assertEqual(health.status, 200)
        self.assertEqual(health.payload["status"], "ok")
        self.assertEqual(health.payload["service"], "airlab")
        self.assertEqual(health.payload["engine_id"], "mock-builder-v2")

        self.assertEqual(capabilities.status, 200)
        self.assertEqual(capabilities.payload["engine_id"], "mock-builder-v2")
        self.assertIn("software", capabilities.payload["task_families"])
        self.assertIn("cad", capabilities.payload["task_families"])
        self.assertIn("gcode", capabilities.payload["artifact_formats"])

    def test_implement_task_returns_same_deterministic_mock_operation(self) -> None:
        body = json.dumps(
            {
                "task": "Create the deterministic staging proof",
                "project_id": "cloudflare-smoke",
                "target": "web",
                "mode": "implement",
                "task_family": "software",
                "task_kind": "software.build",
                "inputs": [],
                "requested_artifacts": [],
                "context": {},
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.payload["status"], "ok")
        self.assertEqual(result.payload["engine_id"], "mock-builder-v2")
        self.assertEqual(len(result.payload["operations"]), 1)
        operation = result.payload["operations"][0]
        self.assertEqual(operation["action"], "create")
        self.assertEqual(operation["path"], ".airlab/mock-result.txt")
        self.assertIn("deterministic staging proof", operation["content"])

    def test_optional_execution_correlation_is_accepted_by_worker_transport(self) -> None:
        body = json.dumps(
            {
                "task": "Create the deterministic staging proof",
                "project_id": "cloudflare-smoke",
                "target": "web",
                "mode": "implement",
                "task_family": "software",
                "task_kind": "software.build",
                "inputs": [],
                "requested_artifacts": [],
                "context": {},
                "execution_correlation": execution_correlation(),
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.payload["status"], "ok")
        self.assertEqual(len(result.payload["operations"]), 1)

    def test_tampered_execution_correlation_is_rejected_by_worker_transport(self) -> None:
        correlation = execution_correlation()
        correlation["idempotency_key"] = "airlab:v1:" + ("0" * 64)
        body = json.dumps(
            {
                "task": "Create the deterministic staging proof",
                "project_id": "cloudflare-smoke",
                "target": "web",
                "mode": "implement",
                "task_family": "software",
                "task_kind": "software.build",
                "inputs": [],
                "requested_artifacts": [],
                "context": {},
                "execution_correlation": correlation,
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 400)
        self.assertIn("idempotency_key", result.payload["error"])

    def test_correlation_must_match_project_and_operation(self) -> None:
        wrong_project = execution_correlation()
        wrong_project["project_id"] = "different-project"
        wrong_project["idempotency_key"] = ExecutionCorrelation.create(
            project_id="different-project",
            task_id="task-42",
            execution_id="execution-123",
            attempt_id="attempt-1",
            operation_id="software.build",
            request_fingerprint=FINGERPRINT,
            checkpoint_id="checkpoint-1",
        ).idempotency_key
        body = json.dumps(
            {
                "task": "Create the deterministic staging proof",
                "project_id": "cloudflare-smoke",
                "target": "web",
                "mode": "implement",
                "task_family": "software",
                "task_kind": "software.build",
                "execution_correlation": wrong_project,
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )
        self.assertEqual(result.status, 400)
        self.assertIn("project_id", result.payload["error"])

        wrong_operation = ExecutionCorrelation.create(
            project_id="cloudflare-smoke",
            task_id="task-42",
            execution_id="execution-123",
            attempt_id="attempt-1",
            operation_id="software.test",
            request_fingerprint=FINGERPRINT,
            checkpoint_id="checkpoint-1",
        ).to_json()
        body = json.dumps(
            {
                "task": "Create the deterministic staging proof",
                "project_id": "cloudflare-smoke",
                "target": "web",
                "mode": "implement",
                "task_family": "software",
                "task_kind": "software.build",
                "execution_correlation": wrong_operation,
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )
        self.assertEqual(result.status, 400)
        self.assertIn("operation_id", result.payload["error"])

    def test_manufacturing_gcode_still_requires_printer_profile(self) -> None:
        body = json.dumps(
            {
                "task": "Slice part",
                "target": "printer",
                "mode": "implement",
                "task_family": "manufacturing",
                "task_kind": "manufacturing.slice",
                "requested_artifacts": ["gcode"],
                "context": {},
            }
        )

        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body=body,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 400)
        self.assertIn("printer_profile", result.payload["error"])

    def test_request_body_limit_is_preserved(self) -> None:
        result = dispatch_cloudflare_request(
            service(),
            method="POST",
            path="/v1/tasks",
            authorization=AUTH,
            body="x" * 1_000_001,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 400)
        self.assertEqual(result.payload, {"error": "invalid request size"})

    def test_unknown_route_does_not_leak_details(self) -> None:
        result = dispatch_cloudflare_request(
            service(),
            method="GET",
            path="/private/debug",
            authorization=AUTH,
            body=None,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 404)
        self.assertEqual(result.payload, {"error": "not_found"})


if __name__ == "__main__":
    unittest.main()
