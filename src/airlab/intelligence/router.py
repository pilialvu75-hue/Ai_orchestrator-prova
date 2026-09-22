from __future__ import annotations

from .contracts import RouteCandidate, RouteDecision, RouteRequest
from .registry import CapabilityRegistry, ProviderRegistry
from .resource_pool import ResourcePoolBridge


class RoutingError(RuntimeError):
    pass


_PRIVACY_RANK = {"standard": 0, "no_training": 1, "local_only": 2}
_FREE_ACCESS = {
    "recurring_free",
    "development_free",
    "account_dependent_free",
}


class IntelligenceRouter:
    def __init__(
        self,
        *,
        capabilities: CapabilityRegistry,
        providers: ProviderRegistry,
        resource_pool: ResourcePoolBridge | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._providers = providers
        self._resource_pool = resource_pool

    def route(self, request: RouteRequest) -> RouteDecision:
        try:
            capability = self._capabilities.require(request.capability)
        except KeyError as exc:
            raise RoutingError(f"unknown capability: {request.capability}") from exc

        candidates: list[RouteCandidate] = []
        rejected: dict[str, tuple[str, ...]] = {}
        minimum_context = max(
            request.required_context_tokens,
            capability.minimum_context_tokens,
        )

        for provider in self._providers.all():
            reasons: list[str] = []
            if not provider.supports(request.capability):
                rejected[provider.provider_id] = ("capability_mismatch",)
                continue

            if self._resource_pool is not None:
                resource_failures = self._resource_pool.rejection_reasons(
                    provider.provider_id,
                    request.capability,
                    request.policy,
                )
                if resource_failures:
                    rejected[provider.provider_id] = resource_failures
                    continue

            health = self._providers.health(provider.provider_id)
            failures = self._rejection_reasons(
                provider=provider,
                health=health,
                minimum_context=minimum_context,
                capability=capability,
                request=request,
            )
            if failures:
                rejected[provider.provider_id] = tuple(failures)
                continue

            score = 100.0
            reasons.append("capability_match")

            if request.policy.free_first:
                if provider.cost_class == "free":
                    score += 800.0
                    reasons.append("free_first")
                elif provider.access_class in _FREE_ACCESS:
                    score += 500.0
                    reasons.append("free_access")

            complexity = max(0.0, min(1.0, request.task_complexity))
            score += provider.quality_score * (120.0 + 120.0 * complexity)
            reasons.append("quality")

            score += self._providers.health(provider.provider_id).success_rate * 60.0
            reasons.append("health")

            observed_latency = health.average_latency_ms
            latency = observed_latency or (
                float(provider.expected_latency_ms)
                if provider.expected_latency_ms is not None
                else None
            )
            if latency is not None:
                score -= min(120.0, latency / 500.0)
                reasons.append("latency")

            score -= max(0.0, min(1.0, provider.historical_error_rate)) * 100.0
            if self._resource_pool is not None:
                resource_priority = self._resource_pool.priority_for(
                    provider.provider_id,
                    request.capability,
                )
            else:
                resource_priority = None
            effective_priority = (
                resource_priority if resource_priority is not None else provider.priority
            )
            score += max(0.0, 100.0 - float(effective_priority))
            if resource_priority is not None:
                reasons.append("resource_priority")

            if health.quota_remaining is not None:
                score += min(50.0, max(0.0, health.quota_remaining))
                reasons.append("quota")

            candidates.append(
                RouteCandidate(
                    provider_id=provider.provider_id,
                    score=round(score, 3),
                    reasons=tuple(reasons),
                )
            )

        candidates.sort(key=lambda item: (-item.score, item.provider_id))
        return RouteDecision(
            capability=request.capability,
            candidates=tuple(candidates),
            rejected=rejected,
        )

    @staticmethod
    def _rejection_reasons(
        *,
        provider,
        health,
        minimum_context: int,
        capability,
        request: RouteRequest,
    ) -> list[str]:
        failures: list[str] = []
        policy = request.policy

        if health.state not in {"healthy", "degraded"}:
            failures.append(f"health:{health.state}")
        if provider.context_window < minimum_context:
            failures.append("context_window")
        if policy.environment not in provider.allowed_environments:
            failures.append("environment")
        if policy.environment == "commercial":
            if not capability.commercial_usage_allowed or not provider.commercial_allowed:
                failures.append("commercial_policy")
        if _PRIVACY_RANK[provider.privacy_class] < _PRIVACY_RANK[policy.privacy]:
            failures.append("privacy")
        if _PRIVACY_RANK[provider.privacy_class] < _PRIVACY_RANK[capability.privacy_requirement]:
            failures.append("capability_privacy")
        spend_safe_free = (
            provider.cost_class == "free" or provider.access_class in _FREE_ACCESS
        )
        if capability.free_only or policy.free_only:
            if not spend_safe_free:
                failures.append("free_only")
        elif (
            not policy.paid_allowed
            and provider.cost_class in {"paid", "metered", "unknown"}
            and provider.access_class not in _FREE_ACCESS
        ):
            failures.append("spend_policy")
        if health.quota_remaining is not None and health.quota_remaining <= 0:
            failures.append("quota_exhausted")

        max_latency = capability.max_acceptable_latency_ms
        known_latency = provider.expected_latency_ms
        if max_latency is not None and known_latency is not None and known_latency > max_latency:
            failures.append("latency_limit")
        return failures
