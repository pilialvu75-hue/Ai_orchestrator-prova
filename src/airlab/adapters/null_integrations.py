from __future__ import annotations

from airlab.contracts import BuildRequest


class NullModuleLibrary:
    def lookup(self, request: BuildRequest) -> list[str]:
        return []


class NullResearcher:
    def lookup(self, request: BuildRequest) -> list[str]:
        return []


class MemoryDiagnostics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, dict(fields)))
