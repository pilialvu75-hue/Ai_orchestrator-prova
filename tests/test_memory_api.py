from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import (
    MemoryDiagnostics,
    NullModuleLibrary,
    NullResearcher,
)
from airlab.cloudflare_api import dispatch_cloudflare_request
from airlab.http_api import create_server
from airlab.memory import (
    MemoryFabric,
    MemoryHealth,
    MemoryHealthStatus,
    MemoryNode,
    MemoryQuery,
    MemoryRecord,
    MemoryType,
    NodeRole,
    PrivacyLevel,
    ProviderDescriptor,
    SyncReport,
)
from airlab.memory.api import dispatch_memory_request
from airlab.service import BuilderService


TOKEN = "test-token"
AUTH = f"Bearer {TOKEN}"


class _MapMemoryProvider:
    def __init__(self, provider_id: str, *, location: str = "cloud") -> None:
        self._descriptor = ProviderDescriptor(
            provider_id=provider_id,
            location=location,
            allowed_privacy=frozenset(
                {
                    PrivacyLevel.PUBLIC,
                    PrivacyLevel.PROJECT,
                    PrivacyLevel.PRIVATE,
                }
            ),
        )
        self.rows: dict[str, MemoryRecord] = {}

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def write(self, record: MemoryRecord) -> MemoryRecord:
        self.rows[record.id] = record
        return record

    def read(self, record_id: str) -> MemoryRecord | None:
        return self.rows.get(record_id)

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        rows = list(self.rows.values())
        if query.namespace:
            rows = [row for row in rows if row.namespace == query.namespace]
        if query.types:
            rows = [row for row in rows if row.type in query.types]
        if query.subject:
            rows = [row for row in rows if row.subject == query.subject]
        if query.project_id:
            rows = [row for row in rows if row.project_id == query.project_id]
        if query.user_id:
            rows = [row for row in rows if row.user_id == query.user_id]
        if query.agent_id:
            rows = [row for row in rows if row.agent_id == query.agent_id]
        if query.conversation_id:
            rows = [
                row
                for row in rows
                if row.conversation_id == query.conversation_id
            ]
        if query.tags:
            required = set(query.tags)
            rows = [
                row
                for row in rows
                if required.issubset(set(row.tags))
            ]
        if query.text:
            term = query.text.lower()
            rows = [
                row
                for row in rows
                if term in row.subject.lower() or term in row.content.lower()
            ]
        if not query.include_expired:
            rows = [row for row in rows if not row.is_expired()]
        rows.sort(key=lambda row: row.updated_at, reverse=True)
        return rows[: query.limit]

    def sync(self) -> SyncReport:
        return SyncReport(
            provider_id=self._descriptor.provider_id,
            ok=True,
            pushed=len(self.rows),
        )

    def health(self) -> MemoryHealth:
        return MemoryHealth(
            provider_id=self._descriptor.provider_id,
            status=MemoryHealthStatus.HEALTHY,
            readable=True,
            writable=True,
            checked_at=datetime.now(timezone.utc),
            details={"records": len(self.rows)},
        )


def _fabric() -> tuple[MemoryFabric, _MapMemoryProvider]:
    provider = _MapMemoryProvider("shared-cloud")
    return (
        MemoryFabric([MemoryNode(provider, NodeRole.PRIMARY)]),
        provider,
    )


def _builder_service() -> BuilderService:
    return BuilderService(
        engine=MockBuilderEngine(),
        library=NullModuleLibrary(),
        researcher=NullResearcher(),
        diagnostics=MemoryDiagnostics(),
    )


class MemoryApiTest(unittest.TestCase):
    def test_write_read_search_health_and_sync(self) -> None:
        fabric, _ = _fabric()
        record = MemoryRecord.create(
            record_id="00000000-0000-4000-8000-000000000101",
            namespace="airlab.project",
            type=MemoryType.PROJECT,
            subject="project_state",
            content="status=blocked",
            source="cantiere_project_state",
            structured_data={"next_step": "repair build"},
            privacy_level=PrivacyLevel.PROJECT,
            tags=("project", "cantiere"),
            project_id="project-101",
        )

        written = dispatch_memory_request(
            fabric,
            method="POST",
            path="/v1/memory/write",
            payload=record.to_json(),
        )
        self.assertEqual(written.status, 200)
        self.assertEqual(written.payload["record"]["id"], record.id)

        read = dispatch_memory_request(
            fabric,
            method="POST",
            path="/v1/memory/read",
            payload={"id": record.id},
        )
        self.assertEqual(read.status, 200)
        self.assertEqual(
            read.payload["record"]["structured_data"]["next_step"],
            "repair build",
        )

        search = dispatch_memory_request(
            fabric,
            method="POST",
            path="/v1/memory/search",
            payload={
                "namespace": "airlab.project",
                "types": ["project"],
                "project_id": "project-101",
                "tags": ["cantiere"],
                "text": "blocked",
                "limit": 10,
            },
        )
        self.assertEqual(search.status, 200)
        self.assertEqual(
            [item["id"] for item in search.payload["records"]],
            [record.id],
        )

        health = dispatch_memory_request(
            fabric,
            method="GET",
            path="/v1/memory/health",
        )
        self.assertEqual(health.status, 200)
        self.assertEqual(
            health.payload["providers"][0]["status"],
            "healthy",
        )

        sync = dispatch_memory_request(
            fabric,
            method="POST",
            path="/v1/memory/sync",
            payload={},
        )
        self.assertEqual(sync.status, 200)
        self.assertTrue(sync.payload["reports"][0]["ok"])

    def test_remote_boundary_rejects_device_only_and_secret(self) -> None:
        fabric, _ = _fabric()
        for privacy in (PrivacyLevel.DEVICE_ONLY, PrivacyLevel.SECRET):
            with self.subTest(privacy=privacy.value):
                record = MemoryRecord.create(
                    namespace="private",
                    type=MemoryType.LONG_TERM_FACT,
                    subject="local-only",
                    content="must not leave device",
                    source="test",
                    privacy_level=privacy,
                )
                result = dispatch_memory_request(
                    fabric,
                    method="POST",
                    path="/v1/memory/write",
                    payload=record.to_json(),
                )
                self.assertEqual(result.status, 403)
                self.assertEqual(
                    result.payload,
                    {"error": "privacy_not_remote"},
                )

    def test_invalid_checksum_fails_closed(self) -> None:
        fabric, _ = _fabric()
        record = MemoryRecord.create(
            namespace="knowledge",
            type=MemoryType.KNOWLEDGE,
            subject="fact",
            content="validated",
            source="test",
        )
        payload = record.to_json()
        payload["content"] = "tampered"

        result = dispatch_memory_request(
            fabric,
            method="POST",
            path="/v1/memory/write",
            payload=payload,
        )

        self.assertEqual(result.status, 400)
        self.assertEqual(
            result.payload,
            {"error": "invalid_memory_checksum"},
        )

    def test_cloudflare_memory_route_is_fail_closed_until_configured(self) -> None:
        result = dispatch_cloudflare_request(
            _builder_service(),
            method="GET",
            path="/v1/memory/health",
            authorization=AUTH,
            body=None,
            auth_token=TOKEN,
        )

        self.assertEqual(result.status, 503)
        self.assertEqual(
            result.payload,
            {"error": "memory_fabric_unavailable"},
        )

    def test_cloudflare_memory_route_uses_injected_fabric(self) -> None:
        fabric, _ = _fabric()
        record = MemoryRecord.create(
            namespace="knowledge",
            type=MemoryType.KNOWLEDGE,
            subject="shared-fact",
            content="provider neutral",
            source="test",
            privacy_level=PrivacyLevel.PROJECT,
        )

        result = dispatch_cloudflare_request(
            _builder_service(),
            method="POST",
            path="/v1/memory/write",
            authorization=AUTH,
            body=json.dumps(record.to_json()),
            auth_token=TOKEN,
            memory=fabric,
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.payload["record"]["id"], record.id)

    def test_real_http_round_trip_uses_memory_fabric(self) -> None:
        fabric, _ = _fabric()
        server = create_server(
            _builder_service(),
            host="127.0.0.1",
            port=0,
            auth_token=None,
            memory=fabric,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            base_url = f"http://{host}:{port}"

            record = MemoryRecord.create(
                namespace="airlab.project",
                type=MemoryType.PROJECT,
                subject="project_state",
                content="status=running",
                source="cantiere_project_state",
                privacy_level=PrivacyLevel.PROJECT,
                project_id="project-http",
            )
            request = Request(
                f"{base_url}/v1/memory/write",
                data=json.dumps(record.to_json()).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)

            read_request = Request(
                f"{base_url}/v1/memory/read",
                data=json.dumps({"id": record.id}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(read_request, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(body["record"]["project_id"], "project-http")

            with urlopen(
                f"{base_url}/v1/memory/health",
                timeout=2,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(body["providers"][0]["status"], "healthy")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
