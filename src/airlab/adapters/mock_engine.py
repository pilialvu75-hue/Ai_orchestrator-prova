from __future__ import annotations

from airlab.contracts import (
    BuildOperation,
    BuildRequest,
    BuildResponse,
    CapabilitySnapshot,
)


class MockBuilderEngine:
    """Deterministic engine used until a real LLM adapter is certified."""

    engine_id = "mock-builder-v1"

    def capabilities(self) -> CapabilitySnapshot:
        return CapabilitySnapshot(
            service="airlab",
            engine_id=self.engine_id,
            engine_kind="mock",
            hardware_required=False,
            supports_streaming=False,
            supports_tools=False,
            max_context_tokens=None,
        )

    def execute(self, request: BuildRequest, request_id: str) -> BuildResponse:
        normalized = " ".join(request.task.split())
        plan = [
            "inspect reusable modules",
            f"prepare {request.mode} work for target {request.target}",
            "validate the result before publication",
        ]
        operations: list[BuildOperation] = []
        if request.mode == "implement":
            operations.append(
                BuildOperation(
                    action="create",
                    path=".airlab/mock-result.txt",
                    content=f"AIrLab mock execution: {normalized}\n",
                )
            )
        return BuildResponse(
            request_id=request_id,
            status="ok",
            engine_id=self.engine_id,
            plan=plan,
            operations=operations,
            metadata={"mock": True, "task_chars": len(normalized)},
        )
