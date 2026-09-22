from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import (
    MemoryHealth,
    MemoryQuery,
    MemoryRecord,
    PrivacyLevel,
    SyncReport,
)


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    location: str
    allowed_privacy: frozenset[PrivacyLevel]
    durable: bool = True

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if self.location not in {"device", "lan", "cloud"}:
            raise ValueError("provider location must be device, lan or cloud")


class MemoryProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def write(self, record: MemoryRecord) -> MemoryRecord: ...

    def read(self, record_id: str) -> MemoryRecord | None: ...

    def search(self, query: MemoryQuery) -> list[MemoryRecord]: ...

    def sync(self) -> SyncReport: ...

    def health(self) -> MemoryHealth: ...
