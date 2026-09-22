from __future__ import annotations

import unittest

from airlab.intelligence.contracts import (
    CapabilityDescriptor,
    GatewayMessage,
    GatewayRequest,
    ProviderOutput,
    RoutePolicy,
)
from airlab.intelligence.gateway import GatewayUnavailable, IntelligenceGateway
from airlab.intelligence.registry import CapabilityRegistry, ProviderRegistry
from airlab.intelligence.resource_pool import (
    ProviderBinding,
    ResourcePoolBridge,
    provider_descriptor_from_resource,
)
from airlab.resources import (
    ResourceDescriptor,
    ResourceHealth,
    ResourceRegistry,
    UsageClass,
)


class Diagnostics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, fields))


class Adapter:
    def __init__(self, provider_id: str, text: str) -> None:
        self.provider_id = provider_id
        self._text = text

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        return ProviderOutput(text=self._text, model=model)


def resource(
    resource_id: str,
    *,
    health: ResourceHealth,
    priority: int = 10,
    development_only: bool = False,
    usage_classes: tuple[UsageClass, ...] = (
        UsageClass.DEVELOPMENT,
        UsageClass.PROTOTYPING,
    ),
) -> ResourceDescriptor:
    return ResourceDescriptor(
        resource_id=resource_id,
        provider=resource_id,
        capabilities=("llm.reasoning",),
        free_tier=True,
        health=health,
        priority={"llm.reasoning": priority},
        development_only=development_only,
        usage_classes=usage_classes,
    )


def binding(resource_id: str) -> ProviderBinding:
    return ProviderBinding(
        resource_id=resource_id,
        endpoint=f"internal://{resource_id}",
        model=f"{resource_id}-model",
        gateway_capabilities=frozenset({"architecture"}),
        context_window=64_000,
        expected_latency_ms=100,
        quality_score=0.8,
        adapter_id="test",
    )


class IntelligenceResourcePoolTests(unittest.TestCase):
    def test_unknown_resource_fails_closed_until_pool_health_is_proven(self) -> None:
        canonical = ResourceRegistry(
            [resource("provider-a", health=ResourceHealth.UNKNOWN)]
        )
        descriptor = provider_descriptor_from_resource(
            canonical.get("provider-a"),
            binding("provider-a"),
        )
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor]),
            adapters=[Adapter("provider-a", "ok")],
            diagnostics=Diagnostics(),
            resource_pool=ResourcePoolBridge(canonical),
        )

        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="architecture",
                    messages=(GatewayMessage(role="user", content="design"),),
                )
            )

        canonical.update_health("provider-a", ResourceHealth.HEALTHY)
        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="design"),),
            )
        )
        self.assertEqual(response.provider_id, "provider-a")
        self.assertEqual(response.text, "ok")

    def test_resource_pool_priority_is_a_router_input(self) -> None:
        canonical = ResourceRegistry(
            [
                resource("provider-a", health=ResourceHealth.HEALTHY, priority=5),
                resource("provider-b", health=ResourceHealth.HEALTHY, priority=30),
            ]
        )
        descriptors = [
            provider_descriptor_from_resource(canonical.get(provider_id), binding(provider_id))
            for provider_id in ("provider-a", "provider-b")
        ]
        diagnostics = Diagnostics()
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry(descriptors),
            adapters=[
                Adapter("provider-a", "a"),
                Adapter("provider-b", "b"),
            ],
            diagnostics=diagnostics,
            resource_pool=ResourcePoolBridge(canonical),
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="design"),),
            )
        )
        self.assertEqual(response.provider_id, "provider-a")
        route = next(
            fields
            for event, fields in diagnostics.events
            if event == "intelligence_route_decided"
        )
        self.assertIn("resource_priority", route["route_reason"])

    def test_resource_usage_policy_blocks_development_resource_in_commercial(self) -> None:
        canonical = ResourceRegistry(
            [
                resource(
                    "provider-a",
                    health=ResourceHealth.HEALTHY,
                    development_only=True,
                    usage_classes=(
                        UsageClass.DEVELOPMENT,
                        UsageClass.PROTOTYPING,
                        UsageClass.COMMERCIAL,
                    ),
                )
            ]
        )
        descriptor = provider_descriptor_from_resource(
            canonical.get("provider-a"),
            binding("provider-a"),
        )
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor]),
            adapters=[Adapter("provider-a", "should-not-run")],
            diagnostics=Diagnostics(),
            resource_pool=ResourcePoolBridge(canonical),
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


if __name__ == "__main__":
    unittest.main()
