from hashlib import sha256
import unittest

from airlab.execution import (
    ExecutionCorrelation,
    RemoteExecutionEvidence,
    derive_idempotency_key,
    recovery_action_for,
)


class ExecutionCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fingerprint = sha256(b"bounded-request-v1").hexdigest()

    def correlation(self, **overrides: str | None) -> ExecutionCorrelation:
        values: dict[str, str | None] = {
            "project_id": "project-abc",
            "task_id": "task-42",
            "execution_id": "execution-123",
            "attempt_id": "attempt-1",
            "operation_id": "software.build",
            "request_fingerprint": self.fingerprint,
            "checkpoint_id": "checkpoint-1",
        }
        values.update(overrides)
        return ExecutionCorrelation.create(**values)  # type: ignore[arg-type]

    def test_known_cross_language_vector_is_stable(self) -> None:
        key = derive_idempotency_key(
            project_id="project-abc",
            task_id="task-42",
            execution_id="execution-123",
            operation_id="software.build",
            request_fingerprint=self.fingerprint,
        )
        self.assertEqual(
            key,
            "airlab:v1:1637d6cf216f94593ac4e97bbb1bce0841553d46922a2ec754df8a8fe7eca701",
        )

    def test_new_attempt_preserves_external_operation_key(self) -> None:
        first = self.correlation()
        second = first.for_attempt(
            attempt_id="attempt-2",
            checkpoint_id="checkpoint-2",
        )

        self.assertNotEqual(first.attempt_id, second.attempt_id)
        self.assertNotEqual(first.checkpoint_id, second.checkpoint_id)
        self.assertEqual(first.execution_id, second.execution_id)
        self.assertEqual(first.idempotency_key, second.idempotency_key)

    def test_new_execution_operation_or_fingerprint_changes_key(self) -> None:
        baseline = self.correlation()
        different_execution = self.correlation(execution_id="execution-124")
        different_operation = self.correlation(operation_id="software.test")
        different_fingerprint = self.correlation(
            request_fingerprint=sha256(b"bounded-request-v2").hexdigest()
        )

        self.assertNotEqual(
            baseline.idempotency_key,
            different_execution.idempotency_key,
        )
        self.assertNotEqual(
            baseline.idempotency_key,
            different_operation.idempotency_key,
        )
        self.assertNotEqual(
            baseline.idempotency_key,
            different_fingerprint.idempotency_key,
        )

    def test_json_round_trip_preserves_authoritative_identity(self) -> None:
        correlation = self.correlation()
        restored = ExecutionCorrelation.from_json(correlation.to_json())
        self.assertEqual(restored, correlation)

    def test_tampered_idempotency_key_is_rejected(self) -> None:
        payload = self.correlation().to_json()
        payload["idempotency_key"] = "airlab:v1:" + ("0" * 64)

        with self.assertRaisesRegex(ValueError, "idempotency_key"):
            ExecutionCorrelation.from_json(payload)

    def test_invalid_request_fingerprint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "request_fingerprint"):
            self.correlation(request_fingerprint="not-a-sha256")

    def test_remote_states_map_to_bounded_recovery_actions(self) -> None:
        self.assertEqual(recovery_action_for("accepted"), "watch")
        self.assertEqual(recovery_action_for("running"), "watch")
        self.assertEqual(recovery_action_for("succeeded"), "reuse_result")
        self.assertEqual(
            recovery_action_for("retryable_failure"),
            "retry_same_key",
        )
        self.assertEqual(recovery_action_for("terminal_failure"), "stop")
        self.assertEqual(recovery_action_for("cancelled"), "stop")

    def test_provider_failover_does_not_change_correlation_key(self) -> None:
        correlation = self.correlation()
        first = RemoteExecutionEvidence(
            correlation=correlation,
            state="retryable_failure",
            provider_id="provider-a",
            remote_job_id="job-a",
            detail_code="timeout",
        )
        second = RemoteExecutionEvidence(
            correlation=correlation.for_attempt(attempt_id="attempt-2"),
            state="accepted",
            provider_id="provider-b",
            remote_job_id="job-b",
        )

        self.assertEqual(
            first.correlation.idempotency_key,
            second.correlation.idempotency_key,
        )
        self.assertEqual(first.recovery_action, "retry_same_key")
        self.assertEqual(second.recovery_action, "watch")

    def test_remote_evidence_serializes_only_bounded_execution_metadata(self) -> None:
        evidence = RemoteExecutionEvidence(
            correlation=self.correlation(),
            state="running",
            provider_id="provider-a",
            remote_job_id="job-1",
        )

        payload = evidence.to_json()
        self.assertEqual(payload["state"], "running")
        self.assertEqual(payload["recovery_action"], "watch")
        self.assertNotIn("prompt", payload)
        self.assertNotIn("content", payload)
        self.assertNotIn("secret", payload)


if __name__ == "__main__":
    unittest.main()
