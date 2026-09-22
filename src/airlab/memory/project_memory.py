from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .fabric import MemoryFabric
from .model import MemoryRecord, MemoryType, PrivacyLevel


@dataclass(frozen=True)
class ProjectMemorySnapshot:
    project_id: str
    original_request: str
    requirements: tuple[str, ...] = ()
    decisions: tuple[dict[str, Any], ...] = ()
    plan: tuple[str, ...] = ()
    tasks: tuple[dict[str, Any], ...] = ()
    attempts: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    fixes: tuple[dict[str, Any], ...] = ()
    ci: tuple[dict[str, Any], ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()
    tests: tuple[dict[str, Any], ...] = ()
    status: str = "created"
    completion_criteria: tuple[str, ...] = ()
    last_error: str | None = None
    next_step: str | None = None

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id is required")
        if not self.original_request.strip():
            raise ValueError("original_request is required")

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        # JSON-facing representation is intentionally list based.
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in payload.items()
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProjectMemorySnapshot":
        return cls(
            project_id=str(payload["project_id"]),
            original_request=str(payload["original_request"]),
            requirements=tuple(payload.get("requirements") or ()),
            decisions=tuple(dict(item) for item in payload.get("decisions") or ()),
            plan=tuple(payload.get("plan") or ()),
            tasks=tuple(dict(item) for item in payload.get("tasks") or ()),
            attempts=tuple(dict(item) for item in payload.get("attempts") or ()),
            errors=tuple(dict(item) for item in payload.get("errors") or ()),
            fixes=tuple(dict(item) for item in payload.get("fixes") or ()),
            ci=tuple(dict(item) for item in payload.get("ci") or ()),
            artifacts=tuple(dict(item) for item in payload.get("artifacts") or ()),
            tests=tuple(dict(item) for item in payload.get("tests") or ()),
            status=str(payload.get("status", "created")),
            completion_criteria=tuple(payload.get("completion_criteria") or ()),
            last_error=payload.get("last_error"),
            next_step=payload.get("next_step"),
        )


class ProjectMemoryService:
    """Stores Cantiere project state without taking lifecycle ownership."""

    namespace = "airlab.project"
    subject = "project_state"

    def __init__(self, memory: MemoryFabric) -> None:
        self._memory = memory

    def save(self, snapshot: ProjectMemorySnapshot) -> MemoryRecord:
        record_id = _record_id(snapshot.project_id)
        current = self._memory.read(record_id)
        payload = snapshot.to_payload()
        content = _summary(snapshot)

        if current is None:
            record = MemoryRecord.create(
                record_id=record_id,
                namespace=self.namespace,
                type=MemoryType.PROJECT,
                subject=self.subject,
                content=content,
                structured_data=payload,
                source="cantiere_project_state",
                privacy_level=PrivacyLevel.PROJECT,
                tags=("project", "cantiere", "checkpoint"),
                project_id=snapshot.project_id,
            )
        else:
            record = current.next_version(
                content=content,
                structured_data=payload,
                source="cantiere_project_state",
            )
        return self._memory.write(record)

    def load(self, project_id: str) -> ProjectMemorySnapshot | None:
        record = self._memory.read(_record_id(project_id))
        if record is None:
            return None
        return ProjectMemorySnapshot.from_payload(record.structured_data)


def _record_id(project_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"airlab-project-memory:{project_id.strip()}"))


def _summary(snapshot: ProjectMemorySnapshot) -> str:
    next_step = snapshot.next_step or "unspecified"
    last_error = snapshot.last_error or "none"
    return (
        f"Project {snapshot.project_id}: status={snapshot.status}; "
        f"last_error={last_error}; next_step={next_step}"
    )
