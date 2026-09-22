from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass(frozen=True)
class UsageEvent:
    task_id: str
    resource_id: str
    capability: str
    metric: str
    quantity: float
    virtual_cost: float = 0.0
    occurred_at: str | None = None
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("resource_id", self.resource_id),
            ("capability", self.capability),
            ("metric", self.metric),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if self.quantity < 0:
            raise ValueError("quantity must be >= 0")
        if self.virtual_cost < 0:
            raise ValueError("virtual_cost must be >= 0")


class UsageEventSink(Protocol):
    def save(self, event: UsageEvent) -> None: ...


class UsageLedger:
    """Fast local accounting ledger with optional best-effort persistence.

    A persistence outage must not turn a successful provider call into a failed
    task. Sink errors are retained for diagnostics/reconciliation.
    """

    def __init__(
        self,
        events: Iterable[UsageEvent] = (),
        *,
        sink: UsageEventSink | None = None,
    ) -> None:
        self._events = list(events)
        self._sink = sink
        self._sink_errors: list[str] = []

    def record(self, event: UsageEvent) -> None:
        self._events.append(event)
        if self._sink is None:
            return
        try:
            self._sink.save(event)
        except Exception as exc:
            self._sink_errors.append(f"{type(exc).__name__}: {exc}")

    @property
    def events(self) -> tuple[UsageEvent, ...]:
        return tuple(self._events)

    @property
    def sink_errors(self) -> tuple[str, ...]:
        return tuple(self._sink_errors)

    @property
    def total_virtual_cost(self) -> float:
        return sum(event.virtual_cost for event in self._events)

    def usage_by_resource(self) -> dict[str, dict[str, float]]:
        totals: dict[str, dict[str, float]] = {}
        for event in self._events:
            resource_totals = totals.setdefault(event.resource_id, {})
            resource_totals[event.metric] = (
                resource_totals.get(event.metric, 0.0) + event.quantity
            )
        return totals

    def usage_for_task(self, task_id: str) -> tuple[UsageEvent, ...]:
        return tuple(event for event in self._events if event.task_id == task_id)
