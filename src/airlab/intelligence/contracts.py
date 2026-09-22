from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Environment = Literal["personal", "development", "production", "commercial"]
PrivacyClass = Literal["standard", "no_training", "local_only"]
CostClass = Literal["free", "metered", "paid", "unknown"]
AccessClass = Literal[
    "recurring_free",
    "development_free",
    "account_dependent_free",
    "promo_credit",
    "paid",
    "unknown",
]
HealthState = Literal[
    "healthy",
    "degraded",
    "unavailable",
    "auth_required",
    "rate_limited",
    "quota_exhausted",
    "cooldown",
]
FailureKind = Literal[
    "authentication",
    "rate_limit",
    "quota",
    "timeout",
    "network",
    "provider_unavailable",
    "invalid_request",
    "provider_error",
]


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    minimum_context_tokens: int = 0
    preferred_models: tuple[str, ...] = ()
    fallback_models: tuple[str, ...] = ()
    max_acceptable_latency_ms: int | None = None
    commercial_usage_allowed: bool = True
    free_only: bool = False
    privacy_requirement: PrivacyClass = "standard"
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    endpoint: str
    model: str
    capabilities: frozenset[str]
    context_window: int
    rate_limit_per_minute: int | None = None
    quota_remaining: float | None = None
    availability: HealthState = "healthy"
    expected_latency_ms: int | None = None
    historical_error_rate: float = 0.0
    usage_rights: str = "unknown"
    allowed_environments: frozenset[Environment] = frozenset(
        {"personal", "development"}
    )
    commercial_allowed: bool = False
    cost_class: CostClass = "unknown"
    access_class: AccessClass = "unknown"
    estimated_cost_per_million_tokens_usd: float | None = None
    priority: int = 50
    quality_score: float = 0.5
    privacy_class: PrivacyClass = "standard"
    adapter_id: str = ""

    def supports(self, capability_id: str) -> bool:
        return capability_id in self.capabilities

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = sorted(self.capabilities)
        payload["allowed_environments"] = sorted(self.allowed_environments)
        return payload


@dataclass
class ProviderHealth:
    state: HealthState = "healthy"
    total_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    average_latency_ms: float | None = None
    last_error: str | None = None
    last_failure_kind: FailureKind | None = None
    cooldown_until_monotonic: float | None = None
    quota_remaining: float | None = None
    rate_window_started_monotonic: float | None = None
    requests_in_rate_window: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_requests <= 0:
            return 1.0
        return max(
            0.0,
            min(1.0, (self.total_requests - self.failed_requests) / self.total_requests),
        )

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "consecutive_failures": self.consecutive_failures,
            "average_latency_ms": self.average_latency_ms,
            "last_failure_kind": self.last_failure_kind,
            "success_rate": self.success_rate,
            "cooldown_active": self.cooldown_until_monotonic is not None,
            "quota_remaining": self.quota_remaining,
            "requests_in_rate_window": self.requests_in_rate_window,
        }


@dataclass(frozen=True)
class RoutePolicy:
    environment: Environment = "development"
    free_first: bool = True
    free_only: bool = True
    paid_allowed: bool = False
    privacy: PrivacyClass = "standard"


@dataclass(frozen=True)
class RouteRequest:
    capability: str
    required_context_tokens: int = 0
    task_complexity: float = 0.5
    policy: RoutePolicy = field(default_factory=RoutePolicy)


@dataclass(frozen=True)
class RouteCandidate:
    provider_id: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RouteDecision:
    capability: str
    candidates: tuple[RouteCandidate, ...]
    rejected: dict[str, tuple[str, ...]]

    @property
    def selected_provider_id(self) -> str | None:
        return self.candidates[0].provider_id if self.candidates else None


@dataclass(frozen=True)
class GatewayMessage:
    role: str
    content: str


@dataclass(frozen=True)
class GatewayRequest:
    capability: str
    messages: tuple[GatewayMessage, ...]
    max_tokens: int = 512
    temperature: float = 0.2
    required_context_tokens: int = 0
    task_complexity: float = 0.5
    policy: RoutePolicy = field(default_factory=RoutePolicy)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderOutput:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayAttempt:
    provider_id: str
    status: Literal["failed", "succeeded"]
    failure_kind: FailureKind | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class GatewayResponse:
    request_id: str
    capability: str
    text: str
    provider_id: str
    model: str
    attempts: tuple[GatewayAttempt, ...]
    usage: dict[str, int] = field(default_factory=dict)
