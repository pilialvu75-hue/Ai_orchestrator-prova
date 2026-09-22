from __future__ import annotations

import time
from collections.abc import Iterable

from .contracts import CapabilityDescriptor, FailureKind, ProviderDescriptor, ProviderHealth


class CapabilityRegistry:
    def __init__(self, capabilities: Iterable[CapabilityDescriptor] = ()) -> None:
        self._items: dict[str, CapabilityDescriptor] = {}
        for descriptor in capabilities:
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        if not descriptor.capability_id.strip():
            raise ValueError("capability_id is required")
        self._items[descriptor.capability_id] = descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._items.get(capability_id)

    def require(self, capability_id: str) -> CapabilityDescriptor:
        descriptor = self.get(capability_id)
        if descriptor is None:
            raise KeyError(capability_id)
        return descriptor

    def all(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


class ProviderRegistry:
    """Gateway execution registry, not the canonical Resource Pool catalog.

    For real providers, static eligibility, usage rights, free-tier state,
    health and multi-metric quota live in airlab.resources.ResourceRegistry.
    This registry keeps invocation metadata plus short-lived circuit/rate state.
    """

    _RATE_LIMIT_COOLDOWN_SECONDS = 120.0
    _QUOTA_COOLDOWN_SECONDS = 900.0
    _TEMPORARY_COOLDOWN_SECONDS = 20.0
    _CIRCUIT_BREAKER_SECONDS = 30.0
    _CIRCUIT_BREAKER_FAILURES = 3

    def __init__(self, providers: Iterable[ProviderDescriptor] = ()) -> None:
        self._providers: dict[str, ProviderDescriptor] = {}
        self._health: dict[str, ProviderHealth] = {}
        for descriptor in providers:
            self.register(descriptor)

    def register(self, descriptor: ProviderDescriptor) -> None:
        if not descriptor.provider_id.strip():
            raise ValueError("provider_id is required")
        self._providers[descriptor.provider_id] = descriptor
        health = self._health.setdefault(
            descriptor.provider_id,
            ProviderHealth(
                state=descriptor.availability,
                quota_remaining=descriptor.quota_remaining,
            ),
        )
        if health.quota_remaining is None and descriptor.quota_remaining is not None:
            health.quota_remaining = descriptor.quota_remaining

    def get(self, provider_id: str) -> ProviderDescriptor | None:
        return self._providers.get(provider_id)

    def all(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def health(self, provider_id: str) -> ProviderHealth:
        if provider_id not in self._providers:
            raise KeyError(provider_id)
        health = self._health.setdefault(provider_id, ProviderHealth())
        self._refresh_cooldown(health)
        return health

    def public_snapshot(self) -> list[dict[str, object]]:
        snapshots: list[dict[str, object]] = []
        for provider in self.all():
            health = self.health(provider.provider_id)
            snapshots.append(
                {
                    "provider_id": provider.provider_id,
                    "model": provider.model,
                    "capabilities": sorted(provider.capabilities),
                    "cost_class": provider.cost_class,
                    "access_class": provider.access_class,
                    "health": health.public_snapshot(),
                }
            )
        return snapshots

    def reserve_request(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise KeyError(provider_id)
        health = self.health(provider_id)
        if health.state not in {"healthy", "degraded"}:
            return False
        if health.quota_remaining is not None and health.quota_remaining <= 0:
            health.state = "quota_exhausted"
            return False

        limit = provider.rate_limit_per_minute
        if limit is None:
            return True
        if limit <= 0:
            health.state = "rate_limited"
            health.cooldown_until_monotonic = time.monotonic() + 60.0
            return False

        now = time.monotonic()
        window_start = health.rate_window_started_monotonic
        if window_start is None or now - window_start >= 60.0:
            health.rate_window_started_monotonic = now
            health.requests_in_rate_window = 0

        if health.requests_in_rate_window >= limit:
            health.state = "rate_limited"
            start = health.rate_window_started_monotonic or now
            health.cooldown_until_monotonic = max(now, start + 60.0)
            return False

        health.requests_in_rate_window += 1
        return True

    def update_quota(
        self,
        provider_id: str,
        remaining: float | None,
        *,
        reset_after_seconds: float | None = None,
    ) -> None:
        health = self.health(provider_id)
        health.quota_remaining = remaining
        if remaining is not None and remaining <= 0:
            health.state = "quota_exhausted"
            if reset_after_seconds is not None:
                health.cooldown_until_monotonic = (
                    time.monotonic() + max(0.0, reset_after_seconds)
                )
            return
        if health.state == "quota_exhausted":
            health.cooldown_until_monotonic = None
            health.state = "degraded" if health.consecutive_failures else "healthy"

    def record_success(self, provider_id: str, latency_ms: int) -> None:
        health = self.health(provider_id)
        health.total_requests += 1
        health.consecutive_failures = 0
        health.last_error = None
        health.last_failure_kind = None
        health.cooldown_until_monotonic = None
        health.state = "healthy"
        self._record_latency(health, latency_ms)

    def record_failure(
        self,
        provider_id: str,
        *,
        kind: FailureKind,
        message: str,
        latency_ms: int,
        retry_after_seconds: float | None = None,
    ) -> None:
        health = self.health(provider_id)
        health.total_requests += 1
        health.failed_requests += 1
        health.consecutive_failures += 1
        health.last_error = message
        health.last_failure_kind = kind
        self._record_latency(health, latency_ms)

        now = time.monotonic()
        cooldown: float | None = None
        if kind == "authentication":
            health.state = "auth_required"
        elif kind == "rate_limit":
            health.state = "rate_limited"
            cooldown = retry_after_seconds or self._RATE_LIMIT_COOLDOWN_SECONDS
        elif kind == "quota":
            health.state = "quota_exhausted"
            cooldown = retry_after_seconds or self._QUOTA_COOLDOWN_SECONDS
        elif kind in {"timeout", "network", "provider_unavailable"}:
            health.state = "cooldown"
            cooldown = retry_after_seconds or self._TEMPORARY_COOLDOWN_SECONDS
        elif health.consecutive_failures >= self._CIRCUIT_BREAKER_FAILURES:
            health.state = "cooldown"
            cooldown = self._CIRCUIT_BREAKER_SECONDS
        else:
            health.state = "degraded"

        if cooldown is not None:
            health.cooldown_until_monotonic = now + max(0.0, cooldown)

    @staticmethod
    def _record_latency(health: ProviderHealth, latency_ms: int) -> None:
        if latency_ms < 0:
            return
        if health.average_latency_ms is None:
            health.average_latency_ms = float(latency_ms)
        else:
            health.average_latency_ms = (health.average_latency_ms * 0.7) + (
                latency_ms * 0.3
            )

    @staticmethod
    def _refresh_cooldown(health: ProviderHealth) -> None:
        until = health.cooldown_until_monotonic
        if until is None:
            return
        if time.monotonic() < until:
            return
        health.cooldown_until_monotonic = None
        if health.state in {"rate_limited", "quota_exhausted", "cooldown"}:
            health.state = "degraded" if health.consecutive_failures else "healthy"


def default_capability_registry() -> CapabilityRegistry:
    entries = (
        CapabilityDescriptor("chat.general", minimum_context_tokens=4096),
        CapabilityDescriptor(
            "reasoning.fast", minimum_context_tokens=8192, max_acceptable_latency_ms=12_000
        ),
        CapabilityDescriptor(
            "reasoning.deep", minimum_context_tokens=16_000, max_acceptable_latency_ms=90_000
        ),
        CapabilityDescriptor("coding.generate", minimum_context_tokens=16_000),
        CapabilityDescriptor("coding.review", minimum_context_tokens=16_000),
        CapabilityDescriptor("coding.debug", minimum_context_tokens=16_000),
        CapabilityDescriptor("architecture", minimum_context_tokens=32_000),
        CapabilityDescriptor("summarize", minimum_context_tokens=16_000),
        CapabilityDescriptor("classify", minimum_context_tokens=4096),
        CapabilityDescriptor("long_context", minimum_context_tokens=64_000),
        CapabilityDescriptor("research", minimum_context_tokens=16_000),
        CapabilityDescriptor("vision", minimum_context_tokens=8192),
    )
    return CapabilityRegistry(entries)
