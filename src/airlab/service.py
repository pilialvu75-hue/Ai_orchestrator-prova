from __future__ import annotations

from uuid import uuid4

from .contracts import BuildRequest, BuildResponse, CapabilitySnapshot
from .ports import DiagnosticsPort, ModelEngine, ModuleLibraryPort, ResearcherPort


class BuilderService:
    def __init__(
        self,
        *,
        engine: ModelEngine,
        library: ModuleLibraryPort,
        researcher: ResearcherPort,
        diagnostics: DiagnosticsPort,
    ) -> None:
        self._engine = engine
        self._library = library
        self._researcher = researcher
        self._diagnostics = diagnostics

    def capabilities(self) -> CapabilitySnapshot:
        return self._engine.capabilities()

    def execute(self, request: BuildRequest) -> BuildResponse:
        request_id = str(uuid4())
        modules = self._library.lookup(request)
        evidence = self._researcher.lookup(request)
        self._diagnostics.emit(
            "build_started",
            {
                "request_id": request_id,
                "engine_id": self._engine.engine_id,
                "mode": request.mode,
                "target": request.target,
                "module_refs": len(modules),
                "research_refs": len(evidence),
            },
        )
        response = self._engine.execute(request, request_id)
        response.metadata["module_refs"] = len(modules)
        response.metadata["research_refs"] = len(evidence)
        self._diagnostics.emit(
            "build_finished",
            {
                "request_id": request_id,
                "status": response.status,
                "engine_id": response.engine_id,
                "operations": len(response.operations),
            },
        )
        return response
