from __future__ import annotations

from airlab.contracts import (
    ArtifactDescriptor,
    BuildOperation,
    BuildRequest,
    BuildResponse,
    CapabilitySnapshot,
)

_ARTIFACT_ROLES: dict[str, tuple[str, bool]] = {
    "airlab": ("source", True),
    "step": ("exchange", True),
    "scad": ("editable", True),
    "dxf": ("editable", True),
    "svg": ("editable", True),
    "3mf": ("printable", False),
    "stl": ("printable", False),
    "gcode": ("machine", False),
}


class MockBuilderEngine:
    """Deterministic engine used until a real LLM adapter is certified."""

    engine_id = "mock-builder-v2"

    def capabilities(self) -> CapabilitySnapshot:
        return CapabilitySnapshot(
            service="airlab",
            engine_id=self.engine_id,
            engine_kind="mock",
            hardware_required=False,
            supports_streaming=False,
            supports_tools=False,
            max_context_tokens=None,
            task_families=("software", "web", "cad", "manufacturing"),
            input_kinds=("text", "image", "drawing", "file", "measurement", "project"),
            artifact_formats=tuple(_ARTIFACT_ROLES),
        )

    def execute(self, request: BuildRequest, request_id: str) -> BuildResponse:
        normalized = " ".join(request.task.split())
        plan = [
            f"classify {request.task_family} task as {request.task_kind}",
            "inspect reusable modules and prior validated assets",
            f"prepare {request.mode} work for target {request.target}",
            "validate the result before publication",
        ]
        if request.task_family == "cad":
            plan.insert(2, "preserve a parametric/editable master before derived print files")
        if request.task_family == "manufacturing":
            plan.insert(2, "validate machine profile before producing machine-specific output")

        operations: list[BuildOperation] = []
        if request.mode == "implement":
            operations.append(
                BuildOperation(
                    action="create",
                    path=".airlab/mock-result.txt",
                    content=f"AIrLab mock execution: {normalized}\n",
                )
            )

        artifacts: list[ArtifactDescriptor] = []
        if request.task_family == "cad":
            artifacts.append(
                ArtifactDescriptor(
                    format="airlab",
                    role="source",
                    path="project/project.airlab.json",
                    editable=True,
                    derived=False,
                )
            )
        for fmt in request.requested_artifacts:
            role, editable = _ARTIFACT_ROLES.get(fmt, ("report", False))
            artifacts.append(
                ArtifactDescriptor(
                    format=fmt,
                    role=role,  # type: ignore[arg-type]
                    path=f"artifacts/output.{fmt}",
                    editable=editable,
                    derived=True,
                )
            )

        return BuildResponse(
            request_id=request_id,
            status="ok",
            engine_id=self.engine_id,
            plan=plan,
            operations=operations,
            artifacts=artifacts,
            metadata={
                "mock": True,
                "task_chars": len(normalized),
                "task_family": request.task_family,
                "task_kind": request.task_kind,
            },
        )
