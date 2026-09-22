from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .model import (
    QuotaMetric,
    ResourceHealth,
    ResourceRegistry,
)


@dataclass(frozen=True)
class ResourceStateSnapshot:
    resource_id: str
    health: ResourceHealth
    checked_at: str
    availability: str = "unknown"
    quota_remaining: dict[str, float | None] | None = None
    cooldown_until: str | None = None
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("resource_id is required")
        if not self.checked_at.strip():
            raise ValueError("checked_at is required")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")
        for name, remaining in (self.quota_remaining or {}).items():
            if not name.strip():
                raise ValueError("quota metric name is required")
            if remaining is not None and remaining < 0:
                raise ValueError("quota remaining must be >= 0")


class ResourceProbe(Protocol):
    @property
    def resource_id(self) -> str: ...

    def probe(self) -> ResourceStateSnapshot: ...


class ResourceStateStore(Protocol):
    def save(self, snapshot: ResourceStateSnapshot) -> None: ...

    def latest(self, resource_id: str) -> ResourceStateSnapshot | None: ...


class ResourcePoolStateManager:
    """Applies runtime observations and persists them best-effort.

    Routing state must remain usable when a remote/shared memory node is down.
    Persistence failures are exposed for diagnostics and later reconciliation.
    """

    def __init__(
        self,
        *,
        registry: ResourceRegistry,
        store: ResourceStateStore | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._persistence_errors: list[str] = []

    @property
    def persistence_errors(self) -> tuple[str, ...]:
        return tuple(self._persistence_errors)

    def apply(
        self,
        snapshot: ResourceStateSnapshot,
        *,
        persist: bool = True,
    ) -> None:
        current = self._registry.get(snapshot.resource_id)
        if current is None:
            raise KeyError(snapshot.resource_id)

        remaining = snapshot.quota_remaining or {}
        known_metrics = {metric.name for metric in current.quota}
        unknown_metrics = set(remaining).difference(known_metrics)
        if unknown_metrics:
            raise ValueError(
                "snapshot contains unknown quota metrics: "
                + ", ".join(sorted(unknown_metrics))
            )

        quota = tuple(
            replace(metric, remaining=remaining.get(metric.name, metric.remaining))
            for metric in current.quota
        )
        updated = replace(
            current,
            health=snapshot.health,
            last_checked=snapshot.checked_at,
            availability=snapshot.availability,
            quota=quota,
            latency=(
                current.latency
                if snapshot.latency_ms is None
                else f"{snapshot.latency_ms:.0f}ms"
            ),
        )
        self._registry.replace(updated)

        if persist and self._store is not None:
            try:
                self._store.save(snapshot)
            except Exception as exc:
                self._persistence_errors.append(f"{type(exc).__name__}: {exc}")

    def probe(self, probe: ResourceProbe) -> ResourceStateSnapshot:
        snapshot = probe.probe()
        if snapshot.resource_id != probe.resource_id:
            raise ValueError(
                "probe resource_id does not match returned snapshot resource_id"
            )
        self.apply(snapshot)
        return snapshot

    def restore(self, resource_id: str) -> ResourceStateSnapshot | None:
        if self._store is None:
            return None
        try:
            snapshot = self._store.latest(resource_id)
        except Exception as exc:
            self._persistence_errors.append(f"{type(exc).__name__}: {exc}")
            return None
        if snapshot is not None:
            self.apply(snapshot, persist=False)
        return snapshot


def quota_remaining(
    metrics: tuple[QuotaMetric, ...],
) -> dict[str, float | None]:
    return {metric.name: metric.remaining for metric in metrics}
