from __future__ import annotations

import unittest
from dataclasses import replace

from airlab.intelligence.contracts import (
    CapabilityDescriptor,
    GatewayMessage,
    GatewayRequest,
    ProviderOutput,
)
from airlab.intelligence.gateway import (
    GatewayUnavailable,
    IntelligenceGateway,
    ProviderExecutionError,
)
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


class _Diagnostics:
    def emit(self, event: str, fields: dict[str, object]) -> None:
        pass


class _Adapter:
    provider_id = "provider-a"

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        return ProviderOutput(
            text="ok",
            model=model,
            usage={"total_tokens": 12},
        )


class _RateLimitedAdapter:
    provider_id = "provider-a"

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        raise ProviderExecutionError(
            "rate limited",
            kind="rate_limit",
            retry_after_seconds=30,
        )


class _StateStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.snapshots = []

    def save(self, snapshot) -> None:
        if self.fail:
            raise RuntimeError("state store unavailable")
        self.snapshots.append(snapshot)

    def latest(self, resource_id: str):
        for snapshot in reversed(self.snapshots):
            if snapshot.resource_id == resource_id:
                return snapshot
        return None


class _UsageSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def save(self, event) -> None:
        if self.fail:
            raise RuntimeError("usage sink unavailable")
        self.events.append(event)


def _resource(
    *,
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


def _binding() -> ProviderBinding:
    return ProviderBinding(
        resource_id="provider-a",
        endpoint="internal://provider-a",
        model="provider-a-model",
        gateway_capabilities=frozenset({"architecture"}),
        context_window=64_000,
        expected_latency_ms=100,
        quality_score=0.8,
        adapter_id="test",
    )


def _gateway(
    *,
    canonical: ResourceRegistry,
    bridge: ResourcePoolBridge,
    adapter,
    ledger: UsageLedger | None = None,
) -> IntelligenceGateway:
    descriptor = provider_descriptor_from_resource(
        canonical.get("provider-a"),
        _binding(),
    )
    return IntelligenceGateway(
        capabilities=CapabilityRegistry([CapabilityDescriptor("architecture")]),
        providers=ProviderRegistry([descriptor]),
        adapters=[adapter],
        diagnostics=_Diagnostics(),
        resource_pool=bridge,
        usage_ledger=ledger,
    )


class ResourceGatewayConvergenceTests(unittest.TestCase):
    def test_gateway_success_persists_canonical_state_and_usage(self) -> None:
        canonical = ResourceRegistry([_resource()])
        state_store = _StateStore()
        state_manager = ResourcePoolStateManager(
            registry=canonical,
            store=state_store,
        )
        usage_sink = _UsageSink()
        ledger = UsageLedger(sink=usage_sink)
        gateway = _gateway(
            canonical=canonical,
            bridge=ResourcePoolBridge(
                canonical,
                state_manager=state_manager,
            ),
            adapter=_Adapter(),
            ledger=ledger,
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="private prompt"),),
                metadata={"task_id": "task-1"},
            )
        )

        self.assertEqual(response.text, "ok")
        self.assertEqual(len(state_store.snapshots), 1)
        snapshot = state_store.snapshots[0]
        self.assertEqual(snapshot.health, ResourceHealth.HEALTHY)
        self.assertEqual(snapshot.availability, "api_reachable")
        self.assertIsNotNone(snapshot.latency_ms)
        self.assertIsNotNone(canonical.get("provider-a").last_checked)

        self.assertEqual(len(usage_sink.events), 2)
        self.assertEqual(usage_sink.events[0].metric, "llm_calls")
        self.assertEqual(usage_sink.events[1].metric, "tokens")
        self.assertNotIn("private prompt", repr(usage_sink.events))

    def test_memory_persistence_outage_does_not_fail_successful_inference(self) -> None:
        canonical = ResourceRegistry([_resource()])
        state_manager = ResourcePoolStateManager(
            registry=canonical,
            store=_StateStore(fail=True),
        )
        ledger = UsageLedger(sink=_UsageSink(fail=True))
        gateway = _gateway(
            canonical=canonical,
            bridge=ResourcePoolBridge(
                canonical,
                state_manager=state_manager,
            ),
            adapter=_Adapter(),
            ledger=ledger,
        )

        response = gateway.complete(
            GatewayRequest(
                capability="architecture",
                messages=(GatewayMessage(role="user", content="go"),),
            )
        )

        self.assertEqual(response.text, "ok")
        self.assertTrue(state_manager.persistence_errors)
        self.assertTrue(ledger.sink_errors)
        self.assertEqual(len(ledger.events), 2)

    def test_rate_limit_cooldown_is_shared_with_canonical_pool(self) -> None:
        canonical = ResourceRegistry([_resource()])
        state_store = _StateStore()
        state_manager = ResourcePoolStateManager(
            registry=canonical,
            store=state_store,
        )
        gateway = _gateway(
            canonical=canonical,
            bridge=ResourcePoolBridge(
                canonical,
                state_manager=state_manager,
            ),
            adapter=_RateLimitedAdapter(),
        )

        with self.assertRaises(GatewayUnavailable):
            gateway.complete(
                GatewayRequest(
                    capability="architecture",
                    messages=(GatewayMessage(role="user", content="go"),),
                )
            )

        current = canonical.get("provider-a")
        self.assertEqual(current.health, ResourceHealth.RATE_LIMITED)
        self.assertIsNotNone(current.cooldown_until)
        self.assertIsNone(canonical.select("llm.reasoning"))
        self.assertEqual(state_store.snapshots[-1].health, ResourceHealth.RATE_LIMITED)

    def test_expired_transient_cooldown_reopens_only_as_degraded(self) -> None:
        canonical = ResourceRegistry([_resource(health=ResourceHealth.RATE_LIMITED)])
        current = canonical.get("provider-a")
        canonical.replace(
            replace(
                current,
                cooldown_until="2000-01-01T00:00:00Z",
            )
        )

        selected = canonical.select("llm.reasoning")

        self.assertIsNotNone(selected)
        self.assertEqual(selected.health, ResourceHealth.DEGRADED)
        self.assertIsNone(selected.cooldown_until)

    def test_expired_cooldown_does_not_revive_exhausted_quota(self) -> None:
        canonical = ResourceRegistry([_resource(health=ResourceHealth.EXHAUSTED)])
        current = canonical.get("provider-a")
        canonical.replace(
            replace(
                current,
                cooldown_until="2000-01-01T00:00:00Z",
            )
        )

        self.assertIsNone(canonical.select("llm.reasoning"))
        self.assertEqual(
            canonical.get("provider-a").health,
            ResourceHealth.EXHAUSTED,
        )


if __name__ == "__main__":
    unittest.main()
