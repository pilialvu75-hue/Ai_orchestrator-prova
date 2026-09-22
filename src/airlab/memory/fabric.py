from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .model import (
    MemoryHealth,
    MemoryQuery,
    MemoryRecord,
    NodeRole,
    PrivacyLevel,
    ReplicationReport,
    SyncReport,
)
from .provider import MemoryProvider


class MemoryPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryNode:
    provider: MemoryProvider
    role: NodeRole
    priority: int = 100
    allowed_privacy: frozenset[PrivacyLevel] | None = None

    def accepts(self, privacy: PrivacyLevel) -> bool:
        node_levels = self.allowed_privacy
        if node_levels is not None and privacy not in node_levels:
            return False
        return privacy in self.provider.descriptor.allowed_privacy


class MemoryFabric:
    """Stable application facade over additive memory nodes.

    Applications depend on this object, never on Supabase/NAS/SQLite directly.
    Providers can be added or removed without changing the public operations.
    """

    def __init__(self, nodes: Iterable[MemoryNode]) -> None:
        self._nodes = tuple(
            sorted(
                nodes,
                key=lambda node: (
                    _role_rank(node.role),
                    node.priority,
                    node.provider.descriptor.provider_id,
                ),
            )
        )
        if not self._nodes:
            raise ValueError("MemoryFabric requires at least one node")

    def write(self, record: MemoryRecord) -> MemoryRecord:
        candidates = [
            node
            for node in self._nodes
            if node.role != NodeRole.READ_ONLY and node.accepts(record.privacy_level)
        ]
        if not candidates:
            raise MemoryPolicyError(
                f"no writable memory node accepts privacy={record.privacy_level.value}"
            )

        succeeded: list[MemoryNode] = []
        failed: dict[str, str] = {}
        for node in candidates:
            provider_id = node.provider.descriptor.provider_id
            try:
                node.provider.write(record)
                succeeded.append(node)
            except Exception as exc:  # provider failure must not collapse the fabric
                failed[provider_id] = str(exc)

        if not succeeded:
            raise RuntimeError(
                "all eligible memory nodes rejected the write: "
                + ", ".join(f"{key}={value}" for key, value in failed.items())
            )

        state = {
            node.provider.descriptor.provider_id: (
                "synced" if node in succeeded else "failed"
            )
            for node in candidates
        }
        final = replace(record, replication_state=state)

        # Best-effort persist the final replication metadata on nodes that
        # accepted the payload. Failure here does not invalidate the durable
        # copy already written.
        for node in succeeded:
            try:
                node.provider.write(final)
            except Exception:
                pass
        return final

    def read(self, record_id: str) -> MemoryRecord | None:
        for node in self._nodes:
            try:
                record = node.provider.read(record_id)
            except Exception:
                continue
            if record is None or record.is_expired():
                continue
            if not record.checksum_valid():
                # Corrupted copies are skipped so a healthy replica can win.
                continue
            return record
        return None

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        winners: dict[str, MemoryRecord] = {}
        for node in self._nodes:
            try:
                records = node.provider.search(query)
            except Exception:
                continue
            for record in records:
                if (not query.include_expired and record.is_expired()) or not record.checksum_valid():
                    continue
                existing = winners.get(record.id)
                if existing is None or (record.version, record.updated_at) > (
                    existing.version,
                    existing.updated_at,
                ):
                    winners[record.id] = record

        ordered = sorted(
            winners.values(),
            key=lambda record: (record.updated_at, record.version),
            reverse=True,
        )
        return ordered[: query.limit]

    def sync(self) -> tuple[SyncReport, ...]:
        reports: list[SyncReport] = []
        for node in self._nodes:
            try:
                reports.append(node.provider.sync())
            except Exception as exc:
                reports.append(
                    SyncReport(
                        provider_id=node.provider.descriptor.provider_id,
                        ok=False,
                        details={"error": str(exc)},
                    )
                )
        return tuple(reports)

    def health(self) -> tuple[MemoryHealth, ...]:
        results: list[MemoryHealth] = []
        for node in self._nodes:
            try:
                results.append(node.provider.health())
            except Exception as exc:
                from datetime import datetime, timezone
                from .model import MemoryHealthStatus

                results.append(
                    MemoryHealth(
                        provider_id=node.provider.descriptor.provider_id,
                        status=MemoryHealthStatus.UNAVAILABLE,
                        readable=False,
                        writable=False,
                        checked_at=datetime.now(timezone.utc),
                        details={"error": str(exc)},
                    )
                )
        return tuple(results)

    def replicate(
        self,
        record_id: str,
        *,
        source_provider_id: str | None = None,
    ) -> ReplicationReport:
        source_record: MemoryRecord | None = None
        for node in self._nodes:
            provider_id = node.provider.descriptor.provider_id
            if source_provider_id is not None and provider_id != source_provider_id:
                continue
            try:
                source_record = node.provider.read(record_id)
            except Exception:
                continue
            if source_record is not None and source_record.checksum_valid():
                break

        if source_record is None:
            return ReplicationReport(
                record_id=record_id,
                attempted=(),
                succeeded=(),
                failed={"source": "record not found on a readable node"},
            )

        attempted: list[str] = []
        succeeded: list[str] = []
        failed: dict[str, str] = {}
        for node in self._nodes:
            provider_id = node.provider.descriptor.provider_id
            if source_provider_id is not None and provider_id == source_provider_id:
                continue
            if node.role == NodeRole.READ_ONLY or not node.accepts(
                source_record.privacy_level
            ):
                continue
            attempted.append(provider_id)
            try:
                node.provider.write(source_record)
                succeeded.append(provider_id)
            except Exception as exc:
                failed[provider_id] = str(exc)

        return ReplicationReport(
            record_id=record_id,
            attempted=tuple(attempted),
            succeeded=tuple(succeeded),
            failed=failed,
        )


def _role_rank(role: NodeRole) -> int:
    return {
        NodeRole.PRIMARY: 0,
        NodeRole.SECONDARY: 1,
        NodeRole.READ_ONLY: 2,
        NodeRole.OFFLINE_CACHE: 3,
    }[role]
