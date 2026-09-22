import unittest

from airlab.resources import (
    QuotaMetric,
    ResourceDescriptor,
    ResourceHealth,
    ResourceRegistry,
    UsageClass,
    UsageEvent,
    UsageLedger,
    free_resource_pool_v1,
)


def _resource(
    resource_id: str,
    *,
    capabilities: tuple[str, ...] = ("llm.coding",),
    health: ResourceHealth = ResourceHealth.HEALTHY,
    priority: dict[str, int] | None = None,
    quota: tuple[QuotaMetric, ...] = (),
    development_only: bool = False,
    usage_classes: tuple[UsageClass, ...] = (
        UsageClass.DEVELOPMENT,
        UsageClass.PROTOTYPING,
    ),
) -> ResourceDescriptor:
    return ResourceDescriptor(
        resource_id=resource_id,
        provider=resource_id,
        capabilities=capabilities,
        free_tier=True,
        health=health,
        priority=priority or {"*": 100},
        quota=quota,
        development_only=development_only,
        usage_classes=usage_classes,
    )


class ResourcePoolTests(unittest.TestCase):
    def test_catalog_covers_v1_resource_families(self) -> None:
        resource_ids = {resource.resource_id for resource in free_resource_pool_v1().all()}
        self.assertTrue(
            {
                "openrouter_free_pool",
                "github_actions_standard",
                "supabase_free",
                "cloudflare_workers_free",
                "inngest_hobby",
                "posthog_free",
                "github_issues",
            }.issubset(resource_ids)
        )

    def test_catalog_never_claims_unprobed_remote_resource_is_healthy(self) -> None:
        pool = free_resource_pool_v1()
        self.assertTrue(pool.all())
        self.assertTrue(
            all(resource.health is ResourceHealth.UNKNOWN for resource in pool.all())
        )

    def test_unknown_health_fails_closed_unless_explicitly_allowed(self) -> None:
        pool = ResourceRegistry(
            [_resource("candidate", health=ResourceHealth.UNKNOWN)]
        )
        self.assertIsNone(pool.select("llm.coding"))
        self.assertEqual(
            pool.select("llm.coding", allow_unknown_health=True).resource_id,
            "candidate",
        )

    def test_ranking_is_capability_specific_not_global(self) -> None:
        pool = ResourceRegistry(
            [
                _resource(
                    "coding_first",
                    capabilities=("llm.coding", "llm.reasoning"),
                    priority={"llm.coding": 10, "llm.reasoning": 40},
                ),
                _resource(
                    "reasoning_first",
                    capabilities=("llm.coding", "llm.reasoning"),
                    priority={"llm.coding": 40, "llm.reasoning": 10},
                ),
            ]
        )
        self.assertEqual(pool.select("llm.coding").resource_id, "coding_first")
        self.assertEqual(
            pool.select("llm.reasoning").resource_id,
            "reasoning_first",
        )

    def test_rate_limited_resource_falls_back(self) -> None:
        pool = ResourceRegistry(
            [
                _resource(
                    "primary",
                    health=ResourceHealth.RATE_LIMITED,
                    priority={"llm.coding": 1},
                ),
                _resource(
                    "fallback",
                    health=ResourceHealth.HEALTHY,
                    priority={"llm.coding": 2},
                ),
            ]
        )
        self.assertEqual(pool.select("llm.coding").resource_id, "fallback")

    def test_exhausted_quota_resource_falls_back(self) -> None:
        exhausted = QuotaMetric(
            name="requests",
            limit=50,
            remaining=0,
            unit="requests/day",
        )
        pool = ResourceRegistry(
            [
                _resource(
                    "primary",
                    priority={"llm.coding": 1},
                    quota=(exhausted,),
                ),
                _resource(
                    "fallback",
                    priority={"llm.coding": 2},
                ),
            ]
        )
        self.assertEqual(pool.select("llm.coding").resource_id, "fallback")

    def test_development_only_resource_is_blocked_for_production(self) -> None:
        pool = ResourceRegistry(
            [
                _resource(
                    "dev_only",
                    development_only=True,
                    usage_classes=(
                        UsageClass.DEVELOPMENT,
                        UsageClass.PRODUCTION,
                    ),
                )
            ]
        )
        self.assertIsNone(
            pool.select(
                "llm.coding",
                usage_class=UsageClass.PRODUCTION,
            )
        )

    def test_health_can_be_updated_by_runtime_probe(self) -> None:
        pool = ResourceRegistry(
            [_resource("candidate", health=ResourceHealth.UNKNOWN)]
        )
        pool.update_health(
            "candidate",
            ResourceHealth.HEALTHY,
            last_checked="2026-09-22T09:00:00Z",
            availability="api_reachable",
        )
        selected = pool.select("llm.coding")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.resource_id, "candidate")
        self.assertEqual(selected.availability, "api_reachable")

    def test_usage_ledger_records_virtual_cost_without_real_billing(self) -> None:
        ledger = UsageLedger()
        ledger.record(
            UsageEvent(
                task_id="task-x",
                resource_id="github_actions_standard",
                capability="build.android",
                metric="ci_minutes",
                quantity=7,
                virtual_cost=7,
            )
        )
        ledger.record(
            UsageEvent(
                task_id="task-x",
                resource_id="openrouter_free_pool",
                capability="llm.coding",
                metric="llm_calls",
                quantity=3,
                virtual_cost=3,
            )
        )

        self.assertEqual(ledger.total_virtual_cost, 10)
        self.assertEqual(
            ledger.usage_by_resource()["github_actions_standard"]["ci_minutes"],
            7,
        )
        self.assertEqual(len(ledger.usage_for_task("task-x")), 2)


if __name__ == "__main__":
    unittest.main()
