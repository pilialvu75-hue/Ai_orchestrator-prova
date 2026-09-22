from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable


class ResourceHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    EXHAUSTED = "EXHAUSTED"
    DOWN = "DOWN"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class UsageClass(str, Enum):
    PERSONAL = "PERSONAL"
    DEVELOPMENT = "DEVELOPMENT"
    PROTOTYPING = "PROTOTYPING"
    COMMERCIAL = "COMMERCIAL"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True)
class QuotaMetric:
    name: str
    limit: float | None
    remaining: float | None
    unit: str
    reset_period: str | None = None
    source: str | None = None

    @property
    def exhausted(self) -> bool:
        return self.remaining is not None and self.remaining <= 0


@dataclass(frozen=True)
class ResourceDescriptor:
    resource_id: str
    provider: str
    capabilities: tuple[str, ...]
    free_tier: bool
    quota: tuple[QuotaMetric, ...] = ()
    rate_limit: tuple[str, ...] = ()
    reset_period: str | None = None
    availability: str = "unknown"
    latency: str = "unknown"
    region: str = "provider_managed"
    auth_required: bool = True
    commercial_use: str = "unverified"
    development_only: bool = False
    privacy: str = "third_party"
    max_runtime: str | None = None
    memory: str | None = None
    compute: str | None = None
    storage: str | None = None
    context_window: int | None = None
    supported_models: tuple[str, ...] = ()
    health: ResourceHealth = ResourceHealth.UNKNOWN
    last_checked: str | None = None
    replacement_candidates: tuple[str, ...] = ()
    priority: dict[str, int] = field(default_factory=dict)
    usage_classes: tuple[UsageClass, ...] = (
        UsageClass.DEVELOPMENT,
        UsageClass.PROTOTYPING,
    )
    documentation_urls: tuple[str, ...] = ()
    terms_urls: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        resource_id = self.resource_id.strip()
        provider = self.provider.strip()
        capabilities = tuple(dict.fromkeys(c.strip() for c in self.capabilities if c.strip()))
        if not resource_id:
            raise ValueError("resource_id is required")
        if not provider:
            raise ValueError("provider is required")
        if not capabilities:
            raise ValueError("at least one capability is required")
        if any(value < 0 for value in self.priority.values()):
            raise ValueError("priority values must be >= 0")

        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "priority", dict(self.priority))

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def allows_use(self, usage_class: UsageClass) -> bool:
        return usage_class in self.usage_classes

    def priority_for(self, capability: str) -> int:
        return self.priority.get(capability, self.priority.get("*", 1000))

    @property
    def quota_exhausted(self) -> bool:
        return any(metric.exhausted for metric in self.quota)

    def with_health(
        self,
        health: ResourceHealth,
        *,
        last_checked: str | None = None,
        availability: str | None = None,
    ) -> "ResourceDescriptor":
        return replace(
            self,
            health=health,
            last_checked=last_checked or self.last_checked,
            availability=availability or self.availability,
        )


class ResourceRegistry:
    """Provider-neutral catalog plus current resource state.

    Ranking is capability-specific. There is deliberately no global "best"
    provider order.
    """

    _BLOCKED_HEALTH = {
        ResourceHealth.RATE_LIMITED,
        ResourceHealth.EXHAUSTED,
        ResourceHealth.DOWN,
        ResourceHealth.DISABLED,
    }

    _HEALTH_RANK = {
        ResourceHealth.HEALTHY: 0,
        ResourceHealth.DEGRADED: 1,
        ResourceHealth.UNKNOWN: 2,
        ResourceHealth.RATE_LIMITED: 3,
        ResourceHealth.EXHAUSTED: 4,
        ResourceHealth.DOWN: 5,
        ResourceHealth.DISABLED: 6,
    }

    def __init__(self, resources: Iterable[ResourceDescriptor] = ()) -> None:
        self._resources: dict[str, ResourceDescriptor] = {}
        for resource in resources:
            self.register(resource)

    def register(self, resource: ResourceDescriptor) -> None:
        if resource.resource_id in self._resources:
            raise ValueError(f"duplicate resource_id: {resource.resource_id}")
        self._resources[resource.resource_id] = resource

    def replace(self, resource: ResourceDescriptor) -> None:
        if resource.resource_id not in self._resources:
            raise KeyError(resource.resource_id)
        self._resources[resource.resource_id] = resource

    def get(self, resource_id: str) -> ResourceDescriptor | None:
        return self._resources.get(resource_id)

    def all(self) -> tuple[ResourceDescriptor, ...]:
        return tuple(self._resources.values())

    def eligible(
        self,
        capability: str,
        *,
        usage_class: UsageClass = UsageClass.DEVELOPMENT,
        require_free: bool = True,
        allow_unknown_health: bool = False,
    ) -> tuple[ResourceDescriptor, ...]:
        candidates: list[ResourceDescriptor] = []
        for resource in self._resources.values():
            if not resource.supports(capability):
                continue
            if require_free and not resource.free_tier:
                continue
            if not resource.allows_use(usage_class):
                continue
            if resource.development_only and usage_class in {
                UsageClass.COMMERCIAL,
                UsageClass.PRODUCTION,
            }:
                continue
            if resource.health in self._BLOCKED_HEALTH:
                continue
            if resource.health is ResourceHealth.UNKNOWN and not allow_unknown_health:
                continue
            if resource.quota_exhausted:
                continue
            candidates.append(resource)

        candidates.sort(
            key=lambda resource: (
                resource.priority_for(capability),
                self._HEALTH_RANK[resource.health],
                resource.resource_id,
            )
        )
        return tuple(candidates)

    def select(
        self,
        capability: str,
        *,
        usage_class: UsageClass = UsageClass.DEVELOPMENT,
        require_free: bool = True,
        allow_unknown_health: bool = False,
    ) -> ResourceDescriptor | None:
        candidates = self.eligible(
            capability,
            usage_class=usage_class,
            require_free=require_free,
            allow_unknown_health=allow_unknown_health,
        )
        return candidates[0] if candidates else None

    def update_health(
        self,
        resource_id: str,
        health: ResourceHealth,
        *,
        last_checked: str | None = None,
        availability: str | None = None,
    ) -> ResourceDescriptor:
        current = self._resources[resource_id]
        updated = current.with_health(
            health,
            last_checked=last_checked,
            availability=availability,
        )
        self._resources[resource_id] = updated
        return updated
