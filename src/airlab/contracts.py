from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .task_catalog import default_task_kind, validate_task_kind

BuildMode = Literal["plan", "implement", "repair"]
BuildStatus = Literal["ok", "error"]
OperationAction = Literal["create", "update", "delete"]
TaskFamily = Literal["software", "web", "cad", "manufacturing"]
TaskInputKind = Literal["text", "image", "drawing", "file", "measurement", "project"]
ArtifactRole = Literal["source", "editable", "exchange", "printable", "machine", "report"]
ArtifactStatus = Literal["planned", "generated"]


@dataclass(frozen=True)
class TaskInput:
    kind: TaskInputKind
    reference: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "TaskInput":
        if not isinstance(payload, dict):
            raise ValueError("each input must be an object")
        kind = str(payload.get("kind", "")).strip().lower()
        if kind not in {"text", "image", "drawing", "file", "measurement", "project"}:
            raise ValueError("unsupported input kind")
        reference = str(payload.get("reference", "")).strip()
        if not reference:
            raise ValueError("input reference is required")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("input metadata must be an object")
        return cls(kind=kind, reference=reference, metadata=metadata)  # type: ignore[arg-type]


@dataclass(frozen=True)
class BuildRequest:
    task: str
    project_id: str = "default"
    target: str = "web"
    mode: BuildMode = "plan"
    task_family: TaskFamily = "software"
    task_kind: str = ""
    inputs: tuple[TaskInput, ...] = ()
    requested_artifacts: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        task = self.task.strip()
        if not task:
            raise ValueError("task is required")
        object.__setattr__(self, "task", task)

        if self.mode not in {"plan", "implement", "repair"}:
            raise ValueError("mode must be plan, implement or repair")

        family = str(self.task_family).strip().lower()
        if family not in {"software", "web", "cad", "manufacturing"}:
            raise ValueError("unsupported task_family")
        object.__setattr__(self, "task_family", family)

        kind = self.task_kind.strip().lower() or default_task_kind(family)
        validate_task_kind(family, kind)
        object.__setattr__(self, "task_kind", kind)

        artifacts = tuple(
            dict.fromkeys(a.strip().lower() for a in self.requested_artifacts if a.strip())
        )
        object.__setattr__(self, "requested_artifacts", artifacts)

        if "gcode" in artifacts:
            if family != "manufacturing":
                raise ValueError("gcode output requires task_family=manufacturing")
            if not self.context.get("printer_profile"):
                raise ValueError("gcode output requires context.printer_profile")

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "BuildRequest":
        task = str(payload.get("task", "")).strip()
        if not task:
            raise ValueError("task is required")

        context = payload.get("context", {})
        if not isinstance(context, dict):
            raise ValueError("context must be an object")

        raw_inputs = payload.get("inputs", [])
        if not isinstance(raw_inputs, list):
            raise ValueError("inputs must be an array")
        inputs = tuple(TaskInput.from_json(item) for item in raw_inputs)

        raw_artifacts = payload.get("requested_artifacts", [])
        if not isinstance(raw_artifacts, list) or not all(
            isinstance(item, str) for item in raw_artifacts
        ):
            raise ValueError("requested_artifacts must be an array of strings")

        return cls(
            task=task,
            project_id=str(payload.get("project_id", "default")),
            target=str(payload.get("target", "web")),
            mode=str(payload.get("mode", "plan")).strip().lower(),  # type: ignore[arg-type]
            task_family=str(payload.get("task_family", "software")).strip().lower(),  # type: ignore[arg-type]
            task_kind=str(payload.get("task_kind", "")).strip().lower(),
            inputs=inputs,
            requested_artifacts=tuple(raw_artifacts),
            context=context,
        )


@dataclass(frozen=True)
class BuildOperation:
    action: OperationAction
    path: str
    content: str | None = None


@dataclass(frozen=True)
class ArtifactDescriptor:
    format: str
    role: ArtifactRole
    path: str
    editable: bool
    derived: bool
    status: ArtifactStatus = "planned"


@dataclass(frozen=True)
class CapabilitySnapshot:
    service: str
    engine_id: str
    engine_kind: str
    hardware_required: bool
    supports_streaming: bool
    supports_tools: bool
    max_context_tokens: int | None = None
    task_families: tuple[str, ...] = ()
    input_kinds: tuple[str, ...] = ()
    artifact_formats: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildResponse:
    request_id: str
    status: BuildStatus
    engine_id: str
    plan: list[str]
    operations: list[BuildOperation]
    artifacts: list[ArtifactDescriptor] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
