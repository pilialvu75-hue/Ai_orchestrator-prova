from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Mapping

from airlab.memory import (
    MemoryFabric,
    MemoryHealth,
    MemoryHealthStatus,
    MemoryNode,
    MemoryPolicyError,
    MemoryQuery,
    MemoryRecord,
    MemoryType,
    NodeRole,
    PrivacyLevel,
    ProjectMemoryService,
    ProjectMemorySnapshot,
    ProviderDescriptor,
    SupabaseMemoryProvider,
    SyncReport,
)


class FakeSupabaseTransport:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, object]:
        del path, headers
        params = dict(query or {})

        if method.upper() == "POST":
            if not isinstance(body, dict):
                return 400, {"message": "expected object"}
            row = dict(body)
            self.rows[str(row["id"])] = row
            return 201, [dict(row)]

        if method.upper() != "GET":
            return 405, {"message": "unsupported method"}

        rows = [dict(row) for row in self.rows.values()]
        for field in (
            "id",
            "namespace",
            "subject",
            "project_id",
            "user_id",
            "agent_id",
            "conversation_id",
        ):
            value = params.get(field)
            if value and value.startswith("eq."):
                expected = value[3:]
                rows = [row for row in rows if str(row.get(field)) == expected]

        type_filter = params.get("type")
        if type_filter:
            if type_filter.startswith("eq."):
                expected = type_filter[3:]
                rows = [row for row in rows if row.get("type") == expected]
            elif type_filter.startswith("in.(") and type_filter.endswith(")"):
                expected = set(type_filter[4:-1].split(","))
                rows = [row for row in rows if row.get("type") in expected]

        text_filter = params.get("or")
        if text_filter:
            marker = ".ilike.*"
            if marker in text_filter:
                term = text_filter.split(marker, 1)[1].split("*", 1)[0].lower()
                rows = [
                    row
                    for row in rows
                    if term in str(row.get("subject", "")).lower()
                    or term in str(row.get("content", "")).lower()
                ]

        rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        limit = int(params.get("limit", "50"))
        return 200, rows[:limit]


class MapMemoryProvider:
    def __init__(self, provider_id: str, *, fail: bool = False) -> None:
        self._descriptor = ProviderDescriptor(
            provider_id=provider_id,
            location="device",
            allowed_privacy=frozenset(PrivacyLevel),
        )
        self.rows: dict[str, MemoryRecord] = {}
        self.fail = fail

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def write(self, record: MemoryRecord) -> MemoryRecord:
        if self.fail:
            raise ConnectionError("node unavailable")
        self.rows[record.id] = record
        return record

    def read(self, record_id: str) -> MemoryRecord | None:
        if self.fail:
            raise ConnectionError("node unavailable")
        return self.rows.get(record_id)

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        if self.fail:
            raise ConnectionError("node unavailable")
        rows = list(self.rows.values())
        if query.project_id:
            rows = [row for row in rows if row.project_id == query.project_id]
        return rows[: query.limit]

    def sync(self) -> SyncReport:
        if self.fail:
            raise ConnectionError("node unavailable")
        return SyncReport(provider_id=self._descriptor.provider_id, ok=True)

    def health(self) -> MemoryHealth:
        status = (
            MemoryHealthStatus.UNAVAILABLE if self.fail else MemoryHealthStatus.HEALTHY
        )
        return MemoryHealth(
            provider_id=self._descriptor.provider_id,
            status=status,
            readable=not self.fail,
            writable=not self.fail,
            checked_at=datetime.now(timezone.utc),
        )


class MemoryFabricV1Test(unittest.TestCase):
    def test_project_memory_survives_service_recreation(self) -> None:
        transport = FakeSupabaseTransport()

        provider_one = SupabaseMemoryProvider(transport=transport)
        fabric_one = MemoryFabric(
            [MemoryNode(provider_one, NodeRole.PRIMARY)]
        )
        service_one = ProjectMemoryService(fabric_one)

        service_one.save(
            ProjectMemorySnapshot(
                project_id="project-001",
                original_request="Build a simple web application",
                requirements=("offline-safe", "tested"),
                tasks=(
                    {"id": "task-1", "status": "done"},
                    {"id": "task-2", "status": "blocked"},
                ),
                errors=({"code": "BUILD_42", "message": "compile failed"},),
                status="blocked",
                last_error="BUILD_42",
                next_step="repair task-2",
            )
        )

        # Simulate process recreation: no Python service/provider/fabric object
        # from the first process is reused. Only the durable remote store remains.
        provider_two = SupabaseMemoryProvider(transport=transport)
        fabric_two = MemoryFabric(
            [MemoryNode(provider_two, NodeRole.PRIMARY)]
        )
        service_two = ProjectMemoryService(fabric_two)

        recovered = service_two.load("project-001")
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(
            recovered.original_request,
            "Build a simple web application",
        )
        self.assertEqual(recovered.status, "blocked")
        self.assertEqual(recovered.tasks[1]["status"], "blocked")
        self.assertEqual(recovered.last_error, "BUILD_42")
        self.assertEqual(recovered.next_step, "repair task-2")

        service_two.save(
            ProjectMemorySnapshot(
                project_id="project-001",
                original_request=recovered.original_request,
                requirements=recovered.requirements,
                tasks=(
                    {"id": "task-1", "status": "done"},
                    {"id": "task-2", "status": "done"},
                ),
                status="running",
                last_error=None,
                next_step="run validation",
            )
        )

        records = fabric_two.search(
            MemoryQuery(project_id="project-001", types=(MemoryType.PROJECT,))
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].version, 2)
        self.assertEqual(records[0].structured_data["next_step"], "run validation")

    def test_primary_failure_degrades_to_secondary(self) -> None:
        primary = MapMemoryProvider("primary", fail=True)
        secondary = MapMemoryProvider("secondary")
        fabric = MemoryFabric(
            [
                MemoryNode(primary, NodeRole.PRIMARY),
                MemoryNode(secondary, NodeRole.SECONDARY),
            ]
        )

        record = MemoryRecord.create(
            namespace="test",
            type=MemoryType.EXECUTION_HISTORY,
            subject="checkpoint",
            content="safe to resume",
            source="test",
            privacy_level=PrivacyLevel.PROJECT,
            project_id="p1",
        )
        written = fabric.write(record)

        self.assertEqual(written.replication_state["primary"], "failed")
        self.assertEqual(written.replication_state["secondary"], "synced")
        self.assertEqual(fabric.read(record.id), secondary.rows[record.id])

    def test_cloud_only_fabric_rejects_device_only_and_secret(self) -> None:
        provider = SupabaseMemoryProvider(transport=FakeSupabaseTransport())
        fabric = MemoryFabric([MemoryNode(provider, NodeRole.PRIMARY)])

        for privacy in (PrivacyLevel.DEVICE_ONLY, PrivacyLevel.SECRET):
            with self.subTest(privacy=privacy):
                record = MemoryRecord.create(
                    namespace="private",
                    type=MemoryType.LONG_TERM_FACT,
                    subject="local-only",
                    content="must not leave device",
                    source="test",
                    privacy_level=privacy,
                )
                with self.assertRaises(MemoryPolicyError):
                    fabric.write(record)

    def test_replication_skips_corrupted_copy_and_recovers_from_replica(self) -> None:
        primary = MapMemoryProvider("primary")
        secondary = MapMemoryProvider("secondary")
        fabric = MemoryFabric(
            [
                MemoryNode(primary, NodeRole.PRIMARY),
                MemoryNode(secondary, NodeRole.SECONDARY),
            ]
        )

        record = MemoryRecord.create(
            namespace="resilience",
            type=MemoryType.FAILURE_SOLUTION,
            subject="validated-fix",
            content="working copy",
            source="verified_test",
        )
        fabric.write(record)

        primary.rows[record.id] = MemoryRecord.from_json(
            {
                **record.to_json(),
                "content": "corrupted",
                "checksum": record.checksum,
            }
        )

        recovered = fabric.read(record.id)
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered.content, "working copy")

    def test_supabase_health_and_search_contract(self) -> None:
        transport = FakeSupabaseTransport()
        provider = SupabaseMemoryProvider(transport=transport)
        fabric = MemoryFabric([MemoryNode(provider, NodeRole.PRIMARY)])

        fabric.write(
            MemoryRecord.create(
                namespace="knowledge",
                type=MemoryType.KNOWLEDGE,
                subject="router",
                content="provider neutral memory routing",
                source="verified_test",
                tags=("memory", "routing"),
                project_id="p2",
            )
        )

        health = fabric.health()
        self.assertEqual(health[0].status, MemoryHealthStatus.HEALTHY)

        results = fabric.search(
            MemoryQuery(
                project_id="p2",
                text="provider",
                tags=("routing",),
                limit=10,
            )
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].subject, "router")


if __name__ == "__main__":
    unittest.main()
