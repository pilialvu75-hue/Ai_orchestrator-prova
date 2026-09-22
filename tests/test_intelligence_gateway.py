from __future__ import annotations

import json
import unittest

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import (
    MemoryDiagnostics,
    NullModuleLibrary,
    NullResearcher,
)
from airlab.cloudflare_api import dispatch_cloudflare_request
from airlab.intelligence.contracts import (
    CapabilityDescriptor,
    GatewayMessage,
    GatewayRequest,
    ProviderDescriptor,
    ProviderOutput,
    RoutePolicy,
)
from airlab.intelligence.gateway import (
    GatewayUnavailable,
    IntelligenceGateway,
    ProviderExecutionError,
)
from airlab.intelligence.openai_compat import (
    chat_completion_response,
    parse_chat_completion_request,
)
from airlab.intelligence.registry import (
    CapabilityRegistry,
    ProviderRegistry,
    default_capability_registry,
)
from airlab.service import BuilderService


class Diagnostics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, fields))


class FailingProvider:
    provider_id = "provider-a"

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        raise ProviderExecutionError("timeout", kind="timeout", retryable=True)


class WorkingProvider:
    provider_id = "provider-b"

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        return ProviderOutput(
            text="fallback-ok",
            model=model,
            usage={"total_tokens": 7},
        )


def descriptor(
    provider_id: str,
    *,
    priority: int,
    commercial: bool = True,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider_id=provider_id,
        endpoint=f"internal://{provider_id}",
        model=f"{provider_id}-model",
        capabilities=frozenset({"architecture"}),
        context_window=64_000,
        expected_latency_ms=100,
        usage_rights="test",
        allowed_environments=frozenset(
            {"personal", "development", "production", "commercial"}
            if commercial
            else {"personal", "development"}
        ),
        commercial_allowed=commercial,
        cost_class="free",
        access_class="recurring_free",
        priority=priority,
        quality_score=0.9,
        privacy_class="no_training",
    )


def builder_service(diagnostics) -> BuilderService:
    return BuilderService(
        engine=MockBuilderEngine(),
        library=NullModuleLibrary(),
        researcher=NullResearcher(),
        diagnostics=diagnostics,
    )


class IntelligenceGatewayTest(unittest.TestCase):
    def test_default_capability_registry_contains_v1_vocabulary(self) -> None:
        actual = {item.capability_id for item in default_capability_registry().all()}
        self.assertEqual(
            actual,
            {
                "chat.general",
                "reasoning.fast",
                "reasoning.deep",
                "coding.generate",
                "coding.review",
                "coding.debug",
                "architecture",
                "summarize",
                "classify",
                "long_context",
                "research",
                "vision",
            },
        )

    def test_primary_failure_falls_back_and_logs_routing(self) -> None:
        diagnostics = Diagnostics()
        providers = ProviderRegistry(
            [descriptor("provider-a", priority=0), descriptor("provider-b", priority=10)]
        )
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=providers,
            adapters=[FailingProvider(), WorkingProvider()],
            diagnostics=diagnostics,
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="design it"),),
                policy=RoutePolicy(free_only=True, paid_allowed=False),
            )
        )

        self.assertEqual(response.text, "fallback-ok")
        self.assertEqual(response.provider_id, "provider-b")
        self.assertEqual(
            [attempt.provider_id for attempt in response.attempts],
            ["provider-a", "provider-b"],
        )
        self.assertEqual(response.attempts[0].failure_kind, "timeout")
        names = [event for event, _ in diagnostics.events]
        self.assertIn("intelligence_route_decided", names)
        self.assertIn("intelligence_provider_failed", names)
        self.assertIn("intelligence_fallback", names)
        self.assertIn("intelligence_provider_succeeded", names)
        route = next(
            fields
            for event, fields in diagnostics.events
            if event == "intelligence_route_decided"
        )
        self.assertEqual(route["selected_provider_id"], "provider-a")
        self.assertIn("capability_match", route["route_reason"])

        second = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="again"),),
            )
        )
        self.assertEqual(second.provider_id, "provider-b")
        self.assertEqual(len(second.attempts), 1)

    def test_commercial_request_fails_closed_for_development_only_provider(self) -> None:
        diagnostics = Diagnostics()
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry(
                [descriptor("provider-b", priority=0, commercial=False)]
            ),
            adapters=[WorkingProvider()],
            diagnostics=diagnostics,
        )
        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="architecture",
                    messages=(GatewayMessage(role="user", content="commercial"),),
                    policy=RoutePolicy(
                        environment="commercial",
                        free_only=True,
                        paid_allowed=False,
                    ),
                )
            )

    def test_openai_compatible_request_is_capability_driven(self) -> None:
        request = parse_chat_completion_request(
            {
                "model": "ignored-client-model",
                "capability": "coding.review",
                "messages": [{"role": "user", "content": "review this"}],
            }
        )
        self.assertEqual(request.capability, "coding.review")
        self.assertTrue(request.policy.free_only)
        self.assertFalse(request.policy.paid_allowed)

    def test_development_free_access_is_spend_safe_even_when_cost_is_unknown(self) -> None:
        diagnostics = Diagnostics()
        provider = ProviderDescriptor(
            provider_id="provider-b",
            endpoint="internal://provider-b",
            model="provider-b-model",
            capabilities=frozenset({"architecture"}),
            context_window=64_000,
            expected_latency_ms=100,
            usage_rights="development-only",
            allowed_environments=frozenset({"personal", "development"}),
            commercial_allowed=False,
            cost_class="unknown",
            access_class="development_free",
            priority=0,
            quality_score=0.9,
            privacy_class="no_training",
        )
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([provider]),
            adapters=[WorkingProvider()],
            diagnostics=diagnostics,
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="prototype"),),
                policy=RoutePolicy(
                    environment="development",
                    free_only=True,
                    paid_allowed=False,
                ),
            )
        )
        self.assertEqual(response.provider_id, "provider-b")

        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="architecture",
                    messages=(GatewayMessage(role="user", content="commercial"),),
                    policy=RoutePolicy(
                        environment="commercial",
                        free_only=True,
                        paid_allowed=False,
                    ),
                )
            )

    def test_public_response_hides_provider_selection(self) -> None:
        diagnostics = Diagnostics()
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor("provider-b", priority=0)]),
            adapters=[WorkingProvider()],
            diagnostics=diagnostics,
        )
        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="design"),),
            )
        )
        public = chat_completion_response(response)
        self.assertEqual(public["model"], "airlab-gateway")
        self.assertNotIn("provider_id", public["airlab"])
        self.assertEqual(
            public["choices"][0]["message"]["content"],
            "fallback-ok",
        )

    def test_cloudflare_chat_completions_keeps_provider_internal(self) -> None:
        diagnostics = Diagnostics()
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor("provider-b", priority=0)]),
            adapters=[WorkingProvider()],
            diagnostics=diagnostics,
        )
        result = dispatch_cloudflare_request(
            builder_service(diagnostics),
            gateway=gateway,
            method="POST",
            path="/v1/chat/completions",
            authorization="Bearer test-token",
            body=json.dumps(
                {
                    "capability": "architecture",
                    "messages": [{"role": "user", "content": "design"}],
                }
            ),
            auth_token="test-token",
        )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.payload["model"], "airlab-gateway")
        self.assertEqual(
            result.payload["choices"][0]["message"]["content"],
            "fallback-ok",
        )
        self.assertNotIn("provider_id", result.payload["airlab"])

    def test_cloudflare_unknown_post_route_stays_not_found_without_body(self) -> None:
        diagnostics = Diagnostics()
        result = dispatch_cloudflare_request(
            builder_service(diagnostics),
            method="POST",
            path="/private/debug",
            authorization="Bearer test-token",
            body=None,
            auth_token="test-token",
        )
        self.assertEqual(result.status, 404)
        self.assertEqual(result.payload, {"error": "not_found"})


if __name__ == "__main__":
    unittest.main()
