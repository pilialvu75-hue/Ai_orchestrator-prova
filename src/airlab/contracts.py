from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

BuildMode = Literal["plan", "implement", "repair"]
BuildStatus = Literal["ok", "error"]
OperationAction = Literal["create", "update", "delete"]


@dataclass(frozen=True)
class BuildRequest:
    task: str
    project_id: str = "default"
    target: str = "web"
    mode: BuildMode = "plan"
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "BuildRequest":
        task = str(payload.get("task", "")).strip()
        if not task:
            raise ValueError("task is required")
        mode = str(payload.get("mode", "plan"))
        if mode not in {"plan", "implement", "repair"}:
            raise ValueError("mode must be plan, implement or repair")
        context = payload.get("context", {})
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        return cls(
            task=task,
            project_id=str(payload.get("project_id", "default")),
            target=str(payload.get("target", "web")),
            mode=mode,  # type: ignore[arg-type]
            context=context,
        )


@dataclass(frozen=True)
class BuildOperation:
    action: OperationAction
    path: str
    content: str | None = None


@dataclass(frozen=True)
class CapabilitySnapshot:
    service: str
    engine_id: str
    engine_kind: str
    hardware_required: bool
    supports_streaming: bool
    supports_tools: bool
    max_context_tokens: int | None = None


@dataclass(frozen=True)
class BuildResponse:
    request_id: str
    status: BuildStatus
    engine_id: str
    plan: list[str]
    operations: list[BuildOperation]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
