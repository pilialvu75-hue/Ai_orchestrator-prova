import unittest

from airlab.memory import MemoryQuery, MemoryType
from airlab.resources import (
    MemoryResourceStateStore,
    MemoryUsageEventStore,
    QuotaMetric,
    ResourceDescriptor,
    ResourceHealth,
    ResourcePoolStateManager,
    ResourceRegistry,
    ResourceStateSnapshot,
    UsageClass,
    UsageEvent,
)


class _MemoryFabricDouble:
    def __init__(self) -> None:
        self.records = []

    def write(self, record):
        self.records.append(record)
        return record

    def search(self, query: MemoryQuery):
        result = []
        for record in reversed(self.records):
            if query.namespace is not None and record.namespace != query.namespace:
                continue
            if query.types and record.type not in query.types:
                continue
            if query.subject is not None and record.subject != query.subject:
                continue
            if query.tags and not set(query.tags).issubset(record.tags):
                continue
            result.append(record)
        return result[: query.limit]


class _Probe:
    def __init__(self, resource_id: str, snapshot: ResourceStateSnapshot) -> None:
        self._resource_id = resource_id
        self._snapshot = snapshot

    @property
    def resource_id(self) -> str:
        return self._resource_id

    def probe(self) -> ResourceStateSnapshot:
        return self._snapshot


def _registry() -> ResourceRegistry:
    return ResourceRegistry(
        [
            ResourceDescriptor(
                resource_id="provider-a",
                provider="Provider A",
                capabilities=("llm.coding",),
                free_tier=True,
                quota=(
                    QuotaMetric(
                        name="requests",
                        limit=50,
                        remaining=None,
                        unit="requests/day",
                    ),
                ),
                health=ResourceHealth.UNKNOWN,
                priority={"llm.coding": 10},
                usage_classes=(UsageClass.DEVELOPMENT,),
            )
        ]
    )


class ResourceStateTests(unittest.TestCase):
    def test_runtime_snapshot_makes_verified_resource_selectable(self) -> None:
        registry = _registry()
        manager = ResourcePoolStateManager(registry=registry)

        manager.apply(
            ResourceStateSnapshot(
                resource_id="provider-a",
                health=ResourceHealth.HEALTHY,
                checked_at="2026-09-22T10:00:00Z",
                availability="api_reachable",
                quota_remaining={"requests": 7},
                latency_ms=123,
            )
        )

        selected = registry.select("llm.coding")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.resource_id, "provider-a")
        self.assertEqual(selected.health, ResourceHealth.HEALTHY)
        self.assertEqual(selected.quota[0].remaining, 7)
        self.assertEqual(selected.latency, "123ms")

    def test_snapshot_rejects_unknown_quota_metric(self) -> None:
        manager = ResourcePoolStateManager(registry=_registry())
        with self.assertRaises(ValueError):
            manager.apply(
                ResourceStateSnapshot(
                    resource_id="provider-a",
                    health=ResourceHealth.HEALTHY,
                    checked_at="2026-09-22T10:00:00Z",
                    quota_remaining={"invented": 10},
                )
            )

    def test_probe_identity_mismatch_fails_closed(self) -> None:
        manager = ResourcePoolStateManager(registry=_registry())
        probe = _Probe(
            "provider-a",
            ResourceStateSnapshot(
                resource_id="provider-b",
                health=ResourceHealth.HEALTHY,
                checked_at="2026-09-22T10:00:00Z",
            ),
        )
        with self.assertRaises(ValueError):
            manager.probe(probe)

    def test_state_round_trips_through_memory_fabric(self) -> None:
        fabric = _MemoryFabricDouble()
        store = MemoryResourceStateStore(fabric)
        snapshot = ResourceStateSnapshot(
            resource_id="provider-a",
            health=ResourceHealth.DEGRADED,
            checked_at="2026-09-22T10:00:00Z",
            availability="reachable_with_errors",
            quota_remaining={"requests": 12},
            cooldown_until="2026-09-22T10:15:00Z",
            latency_ms=456,
        )

        store.save(snapshot)
        restored = store.latest("provider-a")

        self.assertEqual(restored, snapshot)
        self.assertEqual(
            fabric.records[0].type,
            MemoryType.PROVIDER_RESOURCE_STATE,
        )
        self.assertEqual(fabric.records[0].content, "")

    def test_manager_can_restore_latest_state_without_rewriting_memory(self) -> None:
        fabric = _MemoryFabricDouble()
        store = MemoryResourceStateStore(fabric)
        store.save(
            ResourceStateSnapshot(
                resource_id="provider-a",
                health=ResourceHealth.HEALTHY,
                checked_at="2026-09-22T10:00:00Z",
                availability="api_reachable",
                quota_remaining={"requests": 9},
            )
        )
        count_before = len(fabric.records)
        registry = _registry()
        manager = ResourcePoolStateManager(registry=registry, store=store)

        restored = manager.restore("provider-a")

        self.assertIsNotNone(restored)
        self.assertEqual(len(fabric.records), count_before)
        self.assertEqual(registry.select("llm.coding").resource_id, "provider-a")
        self.assertEqual(registry.get("provider-a").quota[0].remaining, 9)

    def test_usage_event_is_persisted_as_execution_history_without_prompt(self) -> None:
        fabric = _MemoryFabricDouble()
        store = MemoryUsageEventStore(fabric)
        event = UsageEvent(
            task_id="task-1",
            resource_id="provider-a",
            capability="llm.coding",
            metric="llm_calls",
            quantity=3,
            virtual_cost=3,
            occurred_at="2026-09-22T10:01:00Z",
            metadata={"status": "success"},
        )

        store.save(event)

        self.assertEqual(len(fabric.records), 1)
        record = fabric.records[0]
        self.assertEqual(record.type, MemoryType.EXECUTION_HISTORY)
        self.assertEqual(record.content, "")
        self.assertEqual(record.structured_data["virtual_cost"], 3)
        self.assertNotIn("prompt", record.structured_data)


if __name__ == "__main__":
    unittest.main()
