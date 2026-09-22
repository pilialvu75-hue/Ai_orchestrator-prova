from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .contracts import (
    FailureKind,
    GatewayAttempt,
    GatewayRequest,
    GatewayResponse,
    ProviderDescriptor,
    ProviderOutput,
    RouteRequest,
)
from .registry import CapabilityRegistry, ProviderRegistry, default_capability_registry
from .router import IntelligenceRouter, RoutingError


class DiagnosticsSink(Protocol):
    def emit(self, event: str, fields: dict[str, object]) -> None: ...


class IntelligenceProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput: ...


class ProviderExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: FailureKind = "provider_error",
        retryable: bool = True,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class GatewayUnavailable(RuntimeError):
    pass


class IntelligenceGateway:
    def __init__(
        self,
        *,
        capabilities: CapabilityRegistry,
        providers: ProviderRegistry,
        adapters: list[IntelligenceProvider],
        diagnostics: DiagnosticsSink,
    ) -> None:
        self._capabilities = capabilities
        self._providers = providers
        self._adapters = {adapter.provider_id: adapter for adapter in adapters}
        self._diagnostics = diagnostics
        self._router = IntelligenceRouter(
            capabilities=capabilities,
            providers=providers,
        )

    def capabilities_snapshot(self) -> list[dict[str, object]]:
        return [item.to_json() for item in self._capabilities.all()]

    def providers_snapshot(self) -> list[dict[str, object]]:
        return self._providers.public_snapshot()

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        request_id = str(uuid4())
        try:
            decision = self._router.route(
                RouteRequest(
                    capability=request.capability,
                    required_context_tokens=request.required_context_tokens,
                    task_complexity=request.task_complexity,
                    policy=request.policy,
                )
            )
        except RoutingError as exc:
            self._diagnostics.emit(
                "intelligence_route_rejected",
                {
                    "request_id": request_id,
                    "capability": request.capability,
                    "reason": "unknown_capability",
                },
            )
            raise GatewayUnavailable(str(exc)) from exc

        self._diagnostics.emit(
            "intelligence_route_decided",
            {
                "request_id": request_id,
                "capability": request.capability,
                "candidate_count": len(decision.candidates),
                "rejected_count": len(decision.rejected),
                "selected_provider_id": decision.selected_provider_id or "",
                "route_reason": decision.candidates[0].reasons if decision.candidates else (),
            },
        )

        if not decision.candidates:
            raise GatewayUnavailable("no eligible provider")

        attempts: list[GatewayAttempt] = []
        for index, candidate in enumerate(decision.candidates):
            provider = self._providers.get(candidate.provider_id)
            adapter = self._adapters.get(candidate.provider_id)
            if provider is None or adapter is None:
                self._diagnostics.emit(
                    "intelligence_provider_skipped",
                    {
                        "request_id": request_id,
                        "provider_id": candidate.provider_id,
                        "reason": "adapter_missing",
                    },
                )
                continue

            started = time.monotonic()
            try:
                output = adapter.complete(request, model=provider.model)
                latency_ms = int((time.monotonic() - started) * 1000)
                self._providers.record_success(provider.provider_id, latency_ms)
                attempts.append(
                    GatewayAttempt(
                        provider_id=provider.provider_id,
                        status="succeeded",
                        latency_ms=latency_ms,
                    )
                )
                self._diagnostics.emit(
                    "intelligence_provider_succeeded",
                    {
                        "request_id": request_id,
                        "capability": request.capability,
                        "provider_id": provider.provider_id,
                        "model_id": output.model,
                        "latency_ms": latency_ms,
                        "attempt_index": index,
                    },
                )
                return GatewayResponse(
                    request_id=request_id,
                    capability=request.capability,
                    text=output.text,
                    provider_id=provider.provider_id,
                    model=output.model,
                    attempts=tuple(attempts),
                    usage=output.usage,
                )
            except ProviderExecutionError as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                self._providers.record_failure(
                    provider.provider_id,
                    kind=exc.kind,
                    message=str(exc),
                    latency_ms=latency_ms,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                attempts.append(
                    GatewayAttempt(
                        provider_id=provider.provider_id,
                        status="failed",
                        failure_kind=exc.kind,
                        latency_ms=latency_ms,
                    )
                )
                self._diagnostics.emit(
                    "intelligence_provider_failed",
                    {
                        "request_id": request_id,
                        "capability": request.capability,
                        "provider_id": provider.provider_id,
                        "failure_kind": exc.kind,
                        "retryable": exc.retryable,
                        "attempt_index": index,
                    },
                )
                if not exc.retryable:
                    break
                if index + 1 < len(decision.candidates):
                    self._diagnostics.emit(
                        "intelligence_fallback",
                        {
                            "request_id": request_id,
                            "from_provider_id": provider.provider_id,
                            "to_provider_id": decision.candidates[index + 1].provider_id,
                            "failure_kind": exc.kind,
                        },
                    )
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                self._providers.record_failure(
                    provider.provider_id,
                    kind="provider_error",
                    message=type(exc).__name__,
                    latency_ms=latency_ms,
                )
                attempts.append(
                    GatewayAttempt(
                        provider_id=provider.provider_id,
                        status="failed",
                        failure_kind="provider_error",
                        latency_ms=latency_ms,
                    )
                )
                self._diagnostics.emit(
                    "intelligence_provider_failed",
                    {
                        "request_id": request_id,
                        "capability": request.capability,
                        "provider_id": provider.provider_id,
                        "failure_kind": "provider_error",
                        "retryable": True,
                        "attempt_index": index,
                    },
                )

        raise GatewayUnavailable("all eligible providers failed")


@dataclass
class ControlProvider:
    """Deterministic contract oracle. It is not a production intelligence model."""

    provider_id: str = "airlab-control"

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        user_text = next(
            (item.content for item in reversed(request.messages) if item.role == "user"),
            "",
        )
        return ProviderOutput(
            text=f"CONTROL[{request.capability}]: {user_text}",
            model=model,
            usage={},
        )


def create_control_gateway(diagnostics: DiagnosticsSink) -> IntelligenceGateway:
    capabilities = default_capability_registry()
    provider = ProviderDescriptor(
        provider_id="airlab-control",
        endpoint="internal://control",
        model="airlab-control-v1",
        capabilities=frozenset(item.capability_id for item in capabilities.all()),
        context_window=131_072,
        rate_limit_per_minute=None,
        quota_remaining=None,
        availability="healthy",
        expected_latency_ms=1,
        historical_error_rate=0.0,
        usage_rights="contract-test-only",
        allowed_environments=frozenset({"personal", "development"}),
        commercial_allowed=False,
        cost_class="free",
        access_class="recurring_free",
        priority=100,
        quality_score=0.0,
        privacy_class="local_only",
        adapter_id="control",
    )
    providers = ProviderRegistry([provider])
    return IntelligenceGateway(
        capabilities=capabilities,
        providers=providers,
        adapters=[ControlProvider()],
        diagnostics=diagnostics,
    )
