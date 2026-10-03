from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
from typing import Any, Literal, Mapping

RemoteExecutionState = Literal[
    "accepted",
    "running",
    "succeeded",
    "retryable_failure",
    "terminal_failure",
    "cancelled",
]

RecoveryAction = Literal[
    "watch",
    "reuse_result",
    "retry_same_key",
    "stop",
]

_SCHEMA_VERSION = 1
_IDEMPOTENCY_PREFIX = "airlab:v1:"
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_VALID_STATES: frozenset[str] = frozenset(
    {
        "accepted",
        "running",
        "succeeded",
        "retryable_failure",
        "terminal_failure",
        "cancelled",
    }
)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty.")
    if len(normalized) > 512:
        raise ValueError(f"{field_name} is too long.")
    return normalized


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _request_fingerprint(value: object) -> str:
    normalized = _required_text(value, "request_fingerprint").lower()
    if _SHA256_HEX.fullmatch(normalized) is None:
        raise ValueError(
            "request_fingerprint must be a lowercase SHA-256 hex digest."
        )
    return normalized


def derive_idempotency_key(
    *,
    project_id: str,
    task_id: str,
    execution_id: str,
    operation_id: str,
    request_fingerprint: str,
) -> str:
    """Derive the stable external-operation idempotency key.

    Attempt, checkpoint, provider and remote-job identities are intentionally
    excluded. A retry/failover of the same logical external operation must use
    the same key; a new execution, operation or request fingerprint must not.
    """

    identity = {
        "execution_id": _required_text(execution_id, "execution_id"),
        "operation_id": _required_text(operation_id, "operation_id"),
        "project_id": _required_text(project_id, "project_id"),
        "request_fingerprint": _request_fingerprint(request_fingerprint),
        "task_id": _required_text(task_id, "task_id"),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _IDEMPOTENCY_PREFIX + sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ExecutionCorrelation:
    """Subordinate AIrLab identity for one Cantiere-owned external operation.

    Cantiere remains authoritative for Project/Task/Execution/Attempt and
    approval/apply state. AIrLab may carry this identity as execution evidence,
    but it must not mint a replacement lifecycle.
    """

    project_id: str
    task_id: str
    execution_id: str
    attempt_id: str
    operation_id: str
    request_fingerprint: str
    idempotency_key: str
    checkpoint_id: str | None = None
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported execution correlation schema_version: "
                f"{self.schema_version}."
            )

        normalized = {
            "project_id": _required_text(self.project_id, "project_id"),
            "task_id": _required_text(self.task_id, "task_id"),
            "execution_id": _required_text(self.execution_id, "execution_id"),
            "attempt_id": _required_text(self.attempt_id, "attempt_id"),
            "operation_id": _required_text(self.operation_id, "operation_id"),
            "request_fingerprint": _request_fingerprint(
                self.request_fingerprint
            ),
            "checkpoint_id": _optional_text(self.checkpoint_id, "checkpoint_id"),
        }
        for field_name, value in normalized.items():
            object.__setattr__(self, field_name, value)

        expected = derive_idempotency_key(
            project_id=normalized["project_id"],
            task_id=normalized["task_id"],
            execution_id=normalized["execution_id"],
            operation_id=normalized["operation_id"],
            request_fingerprint=normalized["request_fingerprint"],
        )
        supplied = _required_text(self.idempotency_key, "idempotency_key")
        if supplied != expected:
            raise ValueError(
                "idempotency_key does not match the authoritative execution "
                "correlation identity."
            )
        object.__setattr__(self, "idempotency_key", supplied)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        task_id: str,
        execution_id: str,
        attempt_id: str,
        operation_id: str,
        request_fingerprint: str,
        checkpoint_id: str | None = None,
    ) -> "ExecutionCorrelation":
        key = derive_idempotency_key(
            project_id=project_id,
            task_id=task_id,
            execution_id=execution_id,
            operation_id=operation_id,
            request_fingerprint=request_fingerprint,
        )
        return cls(
            project_id=project_id,
            task_id=task_id,
            execution_id=execution_id,
            attempt_id=attempt_id,
            operation_id=operation_id,
            request_fingerprint=request_fingerprint,
            idempotency_key=key,
            checkpoint_id=checkpoint_id,
        )

    def for_attempt(
        self,
        *,
        attempt_id: str,
        checkpoint_id: str | None = None,
    ) -> "ExecutionCorrelation":
        """Carry the same external-operation key into a newer Cantiere attempt."""

        return replace(
            self,
            attempt_id=attempt_id,
            checkpoint_id=checkpoint_id,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "operation_id": self.operation_id,
            "request_fingerprint": self.request_fingerprint,
            "idempotency_key": self.idempotency_key,
            "checkpoint_id": self.checkpoint_id,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ExecutionCorrelation":
        if not isinstance(payload, Mapping):
            raise TypeError("ExecutionCorrelation payload must be an object.")
        return cls(
            schema_version=payload.get("schema_version", _SCHEMA_VERSION),
            project_id=payload.get("project_id"),
            task_id=payload.get("task_id"),
            execution_id=payload.get("execution_id"),
            attempt_id=payload.get("attempt_id"),
            operation_id=payload.get("operation_id"),
            request_fingerprint=payload.get("request_fingerprint"),
            idempotency_key=payload.get("idempotency_key"),
            checkpoint_id=payload.get("checkpoint_id"),
        )


@dataclass(frozen=True)
class RemoteExecutionEvidence:
    """Provider-neutral evidence for a subordinate remote execution/job."""

    correlation: ExecutionCorrelation
    state: RemoteExecutionState
    provider_id: str | None = None
    remote_job_id: str | None = None
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _VALID_STATES:
            raise ValueError(f"Unsupported remote execution state: {self.state}.")
        object.__setattr__(
            self,
            "provider_id",
            _optional_text(self.provider_id, "provider_id"),
        )
        object.__setattr__(
            self,
            "remote_job_id",
            _optional_text(self.remote_job_id, "remote_job_id"),
        )
        object.__setattr__(
            self,
            "detail_code",
            _optional_text(self.detail_code, "detail_code"),
        )

    @property
    def recovery_action(self) -> RecoveryAction:
        return recovery_action_for(self.state)

    def to_json(self) -> dict[str, Any]:
        return {
            "correlation": self.correlation.to_json(),
            "state": self.state,
            "provider_id": self.provider_id,
            "remote_job_id": self.remote_job_id,
            "detail_code": self.detail_code,
            "recovery_action": self.recovery_action,
        }


def recovery_action_for(state: RemoteExecutionState) -> RecoveryAction:
    """Map remote evidence to a fail-closed Cantiere recovery disposition."""

    if state not in _VALID_STATES:
        raise ValueError(f"Unsupported remote execution state: {state}.")
    if state in {"accepted", "running"}:
        return "watch"
    if state == "succeeded":
        return "reuse_result"
    if state == "retryable_failure":
        return "retry_same_key"
    return "stop"
