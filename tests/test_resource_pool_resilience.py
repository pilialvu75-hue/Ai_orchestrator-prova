from __future__ import annotations

import unittest
from dataclasses import replace

from airlab.intelligence.contracts import (
    CapabilityDescriptor,
    GatewayMessage,
    GatewayRequest,
    ProviderOutput,
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
    ResourcePoolStateManager,
    ResourceRegistry,
    UsageClass,
    UsageLedger,
)


class Diagnostics:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, fields: dict[str, object]) -> None:
        self.events.append((event, fields))


class Adapter:
    def __init__(self) -> None:
        self.provider_id = "provider-a"
        self.called = 0

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        self.called += 1
        return ProviderOutput(
            text="ok",
            model=model,
            usage={"total_tokens": 12},
        )


class FailingStateStore:
    def save(self, snapshot) -> None:
        raise RuntimeError("memory unavailable")

    def latest(self, resource_id: str):
        raise RuntimeError("memory unavailable")


class FailingUsageStore:
    def save(self, event) -> None:
        raise RuntimeError("usage memory unavailable")


def resource(
    health: ResourceHealth = ResourceHealth.HEALTHY,
) -> ResourceDescriptor:
    return ResourceDescriptor(
        resource_id="provider-a",
        provider="Provider A",
        capabilities=("llm.reasoning",),
        free_tier=True,
        health=health,
        priority={"llm.reasoning": 10},
        usage_classes=(UsageClass.DEVELOPMENT,),
    )


def binding() -> ProviderBinding:
    return ProviderBinding(
        resource_id="provider-a",
        endpoint="internal://provider-a",
        model="provider-a-model",
        gateway_capabilities=frozenset({"architecture"}),
        context_window=64_000,
        expected_latency_ms=100,
        adapter_id="test",
    )


def request() -> GatewayRequest:
    return GatewayRequest(
        capability="architecture",
        messages=(GatewayMessage(role="user", content="private prompt"),),
        metadata={"task_id": "task-1"},
    )


class ResourcePoolResilienceTests(unittest.TestCase):
    def test_memory_outage_does_not_turn_successful_inference_into_failure(self) -> None:
        canonical = ResourceRegistry([resource()])
        state_manager = ResourcePoolStateManager(
            registry=canonical,
            store=FailingStateStore(),
        )
        bridge = ResourcePoolBridge(
            canonical,
            state_manager=state_manager,
        )
        diagnostics = Diagnostics()
        ledger = UsageLedger()
        adapter = Adapter()
        descriptor = provider_descriptor_from_resource(
            canonical.get("provider-a"),
            binding(),
        )
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor]),
            adapters=[adapter],
            diagnostics=diagnostics,
            resource_pool=bridge,
            usage_ledger=ledger,
            usage_store=FailingUsageStore(),
        )

        response = gateway.complete(request())

        self.assertEqual(response.text, "ok")
        self.assertEqual(adapter.called, 1)
        self.assertEqual(len(ledger.events), 2)
        self.assertTrue(state_manager.persistence_errors)
        self.assertTrue(
            any(
                event == "intelligence_usage_persistence_failed"
                for event, _ in diagnostics.events
            )
        )
        self.assertNotIn("private prompt", repr(diagnostics.events))
        self.assertEqual(
            canonical.get("provider-a").health,
            ResourceHealth.HEALTHY,
        )

    def test_local_rate_capacity_exhaustion_is_shared_with_resource_pool(self) -> None:
        canonical = ResourceRegistry([resource()])
        bridge = ResourcePoolBridge(canonical)
        descriptor = provider_descriptor_from_resource(
            canonical.get("provider-a"),
            binding(),
        )
        descriptor = replace(descriptor, rate_limit_per_minute=0)
        diagnostics = Diagnostics()
        adapter = Adapter()
        gateway = IntelligenceGateway(
            capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
            providers=ProviderRegistry([descriptor]),
            adapters=[adapter],
            diagnostics=diagnostics,
            resource_pool=bridge,
        )

        with self.assertRaises(GatewayUnavailable):
            gateway.complete(request())

        current = canonical.get("provider-a")
        self.assertEqual(adapter.called, 0)
        self.assertEqual(current.health, ResourceHealth.RATE_LIMITED)
        self.assertIsNotNone(current.cooldown_until)
        self.assertIsNone(canonical.select("llm.reasoning"))

    def test_expired_rate_limit_reopens_as_degraded(self) -> None:
        canonical = ResourceRegistry(
            [
                replace(
                    resource(ResourceHealth.RATE_LIMITED),
                    cooldown_until="2000-01-01T00:00:00Z",
                )
            ]
        )

        selected = canonical.select("llm.reasoning")

        self.assertIsNotNone(selected)
        self.assertEqual(selected.health, ResourceHealth.DEGRADED)
        self.assertIsNone(selected.cooldown_until)
        self.assertEqual(
            selected.availability,
            "cooldown_expired_retry_allowed",
        )

    def test_expired_cooldown_never_revives_exhausted_quota(self) -> None:
        canonical = ResourceRegistry(
            [
                replace(
                    resource(ResourceHealth.EXHAUSTED),
                    cooldown_until="2000-01-01T00:00:00Z",
                )
            ]
        )

        self.assertIsNone(canonical.select("llm.reasoning"))
        current = canonical.get("provider-a")
        self.assertEqual(current.health, ResourceHealth.EXHAUSTED)
        self.assertIsNotNone(current.cooldown_until)


if __name__ == "__main__":
    unittest.main()
