from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from airlab.resources import (
    ResourceDescriptor,
    ResourceHealth,
    ResourcePoolStateManager,
    ResourceRegistry,
    ResourceStateSnapshot,
    UsageClass,
)

from .contracts import AccessClass, FailureKind, ProviderDescriptor, RoutePolicy


CAPABILITY_TO_RESOURCE_CAPABILITY: dict[str, str] = {
    "chat.general": "llm.general",
    "reasoning.fast": "llm.reasoning",
    "reasoning.deep": "llm.reasoning",
    "coding.generate": "llm.coding",
    "coding.review": "llm.review",
    "coding.debug": "llm.coding",
    "architecture": "llm.reasoning",
    "summarize": "llm.general",
    "classify": "llm.general",
    "long_context": "llm.general",
    "research": "llm.reasoning",
    "vision": "llm.vision",
}

_ENVIRONMENT_TO_USAGE = {
    "personal": UsageClass.PERSONAL,
    "development": UsageClass.DEVELOPMENT,
    "production": UsageClass.PRODUCTION,
    "commercial": UsageClass.COMMERCIAL,
}

_BLOCKED_RESOURCE_HEALTH = {
    ResourceHealth.RATE_LIMITED,
    ResourceHealth.EXHAUSTED,
    ResourceHealth.DOWN,
    ResourceHealth.DISABLED,
}


@dataclass(frozen=True)
class ProviderBinding:
    """Execution-only binding for a canonical Resource Pool entry.

    Scheduling/legal/quota facts remain owned by ResourceDescriptor. This
    binding contains only what the Intelligence Gateway needs to invoke a model.
    """

    resource_id: str
    endpoint: str
    model: str
    gateway_capabilities: frozenset[str]
    context_window: int | None = None
    expected_latency_ms: int | None = None
    historical_error_rate: float = 0.0
    quality_score: float = 0.5
    access_class: AccessClass = "account_dependent_free"
    adapter_id: str = ""


class ResourcePoolBridge:
    """Translate canonical Resource Pool facts into Gateway routing facts.

    ProviderRegistry keeps fast execution-local circuit-breaker statistics.
    ResourcePoolStateManager, when supplied, owns shared/persisted provider state.
    """

    def __init__(
        self,
        registry: ResourceRegistry,
        *,
        state_manager: ResourcePoolStateManager | None = None,
    ) -> None:
        self.registry = registry
        self._state_manager = state_manager

    def rejection_reasons(
        self,
        provider_id: str,
        gateway_capability: str,
        policy: RoutePolicy,
    ) -> tuple[str, ...]:
        resource = self.registry.get(provider_id)
        if resource is None:
            return ("resource_unregistered",)

        resource_capability = CAPABILITY_TO_RESOURCE_CAPABILITY.get(gateway_capability)
        if resource_capability is None or not resource.supports(resource_capability):
            return ("resource_capability_mismatch",)

        failures: list[str] = []
        usage_class = _ENVIRONMENT_TO_USAGE[policy.environment]
        if not resource.allows_use(usage_class):
            failures.append("resource_usage_class")
        if resource.development_only and usage_class in {
            UsageClass.COMMERCIAL,
            UsageClass.PRODUCTION,
        }:
            failures.append("resource_development_only")

        if resource.health in _BLOCKED_RESOURCE_HEALTH:
            failures.append(f"resource_health:{resource.health.value}")
        elif resource.health is ResourceHealth.UNKNOWN:
            failures.append("resource_health:UNKNOWN")

        if resource.quota_exhausted:
            failures.append("resource_quota_exhausted")

        spend_safe_required = policy.free_only or not policy.paid_allowed
        if spend_safe_required and not resource.free_tier:
            failures.append("resource_not_free")

        return tuple(failures)

    def priority_for(self, provider_id: str, gateway_capability: str) -> int | None:
        resource = self.registry.get(provider_id)
        resource_capability = CAPABILITY_TO_RESOURCE_CAPABILITY.get(gateway_capability)
        if resource is None or resource_capability is None:
            return None
        return resource.priority_for(resource_capability)

    def record_success(
        self,
        provider_id: str,
        *,
        latency_ms: int | None = None,
    ) -> None:
        resource = self.registry.get(provider_id)
        if resource is None:
            return
        if self._state_manager is None:
            self.registry.update_health(
                provider_id,
                ResourceHealth.HEALTHY,
                last_checked=_utc_now(),
                availability="api_reachable",
            )
            return
        self._state_manager.apply(
            ResourceStateSnapshot(
                resource_id=provider_id,
                health=ResourceHealth.HEALTHY,
                checked_at=_utc_now(),
                availability="api_reachable",
                quota_remaining=None,
                cooldown_until=None,
                latency_ms=latency_ms,
            )
        )

    def record_failure(
        self,
        provider_id: str,
        kind: FailureKind,
        *,
        latency_ms: int | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        resource = self.registry.get(provider_id)
        if resource is None:
            return

        if kind == "rate_limit":
            health = ResourceHealth.RATE_LIMITED
            availability = "rate_limited"
        elif kind == "quota":
            health = ResourceHealth.EXHAUSTED
            availability = "quota_exhausted"
        elif kind in {"network", "provider_unavailable"}:
            health = ResourceHealth.DOWN
            availability = "temporarily_unavailable"
        elif kind == "authentication":
            health = ResourceHealth.DEGRADED
            availability = "auth_required"
        elif kind in {"timeout", "provider_error"}:
            health = ResourceHealth.DEGRADED
            availability = "degraded"
        else:
            return

        cooldown_until = _cooldown_until(cooldown_seconds)
        if self._state_manager is None:
            updated = self.registry.update_health(
                provider_id,
                health,
                last_checked=_utc_now(),
                availability=availability,
            )
            if cooldown_until is not None:
                from dataclasses import replace

                self.registry.replace(
                    replace(updated, cooldown_until=cooldown_until)
                )
            return

        self._state_manager.apply(
            ResourceStateSnapshot(
                resource_id=provider_id,
                health=health,
                checked_at=_utc_now(),
                availability=availability,
                quota_remaining=None,
                cooldown_until=cooldown_until,
                latency_ms=latency_ms,
            )
        )


def provider_descriptor_from_resource(
    resource: ResourceDescriptor,
    binding: ProviderBinding,
) -> ProviderDescriptor:
    if resource.resource_id != binding.resource_id:
        raise ValueError("binding resource_id must match ResourceDescriptor")

    mapped_capabilities = frozenset(
        capability
        for capability in binding.gateway_capabilities
        if CAPABILITY_TO_RESOURCE_CAPABILITY.get(capability) in resource.capabilities
    )
    if not mapped_capabilities:
        raise ValueError(
            f"resource {resource.resource_id} does not satisfy any bound Gateway capability"
        )

    allowed_environments: set[str] = set()
    if UsageClass.PERSONAL in resource.usage_classes:
        allowed_environments.add("personal")
    if (
        UsageClass.DEVELOPMENT in resource.usage_classes
        or UsageClass.PROTOTYPING in resource.usage_classes
    ):
        allowed_environments.add("development")
    if UsageClass.PRODUCTION in resource.usage_classes and not resource.development_only:
        allowed_environments.add("production")
    if UsageClass.COMMERCIAL in resource.usage_classes and not resource.development_only:
        allowed_environments.add("commercial")

    commercial_allowed = "commercial" in allowed_environments
    context_window = (
        binding.context_window
        if binding.context_window is not None
        else resource.context_window
    )
    if context_window is None:
        context_window = 4096

    # Live quota remains multi-metric in Resource Pool and is deliberately not
    # flattened into a single incompatible numeric unit here.
    return ProviderDescriptor(
        provider_id=resource.resource_id,
        endpoint=binding.endpoint,
        model=binding.model,
        capabilities=mapped_capabilities,
        context_window=context_window,
        rate_limit_per_minute=None,
        quota_remaining=None,
        availability="healthy",
        expected_latency_ms=binding.expected_latency_ms,
        historical_error_rate=binding.historical_error_rate,
        usage_rights=resource.commercial_use,
        allowed_environments=frozenset(allowed_environments),  # type: ignore[arg-type]
        commercial_allowed=commercial_allowed,
        cost_class="free" if resource.free_tier else "unknown",
        access_class=binding.access_class,
        priority=50,
        quality_score=binding.quality_score,
        privacy_class="standard",
        adapter_id=binding.adapter_id,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cooldown_until(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    value = max(0.0, seconds)
    return (
        datetime.now(timezone.utc) + timedelta(seconds=value)
    ).isoformat().replace("+00:00", "Z")
