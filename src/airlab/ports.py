from __future__ import annotations

from typing import Protocol

from .contracts import BuildRequest, BuildResponse, CapabilitySnapshot


class ModelEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    def capabilities(self) -> CapabilitySnapshot: ...

    def execute(self, request: BuildRequest, request_id: str) -> BuildResponse: ...


class ModuleLibraryPort(Protocol):
    def lookup(self, request: BuildRequest) -> list[str]: ...


class ResearcherPort(Protocol):
    def lookup(self, request: BuildRequest) -> list[str]: ...


class DiagnosticsPort(Protocol):
    def emit(self, event: str, fields: dict[str, object]) -> None: ...
