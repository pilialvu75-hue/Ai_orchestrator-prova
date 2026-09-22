from __future__ import annotations

from typing import Any

from airlab.memory import (
    MemoryFabric,
    MemoryQuery,
    MemoryRecord,
    MemoryType,
    PrivacyLevel,
)

from .accounting import UsageEvent
from .model import ResourceHealth
from .state import ResourceStateSnapshot

_RESOURCE_NAMESPACE = "airlab.resource_pool"


class MemoryResourceStateStore:
    """Persists Resource Pool runtime state through Memory Fabric."""

    def __init__(self, fabric: MemoryFabric) -> None:
        self._fabric = fabric

    def save(self, snapshot: ResourceStateSnapshot) -> None:
        record = MemoryRecord.create(
            namespace=_RESOURCE_NAMESPACE,
            type=MemoryType.PROVIDER_RESOURCE_STATE,
            subject=f"resource:{snapshot.resource_id}",
            content="",
            source="airlab.resource_pool",
            structured_data={
                "resource_id": snapshot.resource_id,
                "health": snapshot.health.value,
                "checked_at": snapshot.checked_at,
                "availability": snapshot.availability,
                "quota_remaining": dict(snapshot.quota_remaining or {}),
                "cooldown_until": snapshot.cooldown_until,
                "latency_ms": snapshot.latency_ms,
            },
            privacy_level=PrivacyLevel.PROJECT,
            tags=("resource_pool", "provider_state", snapshot.resource_id),
        )
        self._fabric.write(record)

    def latest(self, resource_id: str) -> ResourceStateSnapshot | None:
        records = self._fabric.search(
            MemoryQuery(
                namespace=_RESOURCE_NAMESPACE,
                types=(MemoryType.PROVIDER_RESOURCE_STATE,),
                subject=f"resource:{resource_id}",
                tags=("resource_pool", "provider_state", resource_id),
                limit=1,
            )
        )
        if not records:
            return None
        return _snapshot_from_record(records[0])


class MemoryUsageEventStore:
    """Persists zero-euro/virtual usage accounting through Memory Fabric."""

    def __init__(self, fabric: MemoryFabric) -> None:
        self._fabric = fabric

    def save(self, event: UsageEvent) -> None:
        record = MemoryRecord.create(
            namespace=_RESOURCE_NAMESPACE,
            type=MemoryType.EXECUTION_HISTORY,
            subject=f"usage:{event.task_id}:{event.resource_id}",
            content="",
            source="airlab.resource_pool",
            structured_data={
                "task_id": event.task_id,
                "resource_id": event.resource_id,
                "capability": event.capability,
                "metric": event.metric,
                "quantity": event.quantity,
                "virtual_cost": event.virtual_cost,
                "occurred_at": event.occurred_at,
                "metadata": dict(event.metadata),
            },
            privacy_level=PrivacyLevel.PROJECT,
            tags=(
                "resource_pool",
                "usage_event",
                event.resource_id,
                event.capability,
            ),
        )
        self._fabric.write(record)


def _snapshot_from_record(record: MemoryRecord) -> ResourceStateSnapshot:
    data: dict[str, Any] = record.structured_data
    raw_quota = data.get("quota_remaining")
    quota: dict[str, float | None] = {}
    if isinstance(raw_quota, dict):
        for key, value in raw_quota.items():
            quota[str(key)] = None if value is None else float(value)

    latency_value = data.get("latency_ms")
    return ResourceStateSnapshot(
        resource_id=str(data["resource_id"]),
        health=ResourceHealth(str(data["health"])),
        checked_at=str(data["checked_at"]),
        availability=str(data.get("availability", "unknown")),
        quota_remaining=quota,
        cooldown_until=(
            None
            if data.get("cooldown_until") is None
            else str(data["cooldown_until"])
        ),
        latency_ms=(
            None if latency_value is None else float(latency_value)
        ),
    )
