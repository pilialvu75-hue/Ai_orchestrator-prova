from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .fabric import MemoryFabric, MemoryPolicyError
from .model import (
    MemoryQuery,
    MemoryRecord,
    MemoryType,
    PrivacyLevel,
)


@dataclass(frozen=True)
class MemoryApiResult:
    status: int
    payload: dict[str, Any]


_REMOTE_FORBIDDEN = {
    PrivacyLevel.DEVICE_ONLY,
    PrivacyLevel.SECRET,
}


def dispatch_memory_request(
    memory: MemoryFabric,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> MemoryApiResult:
    """Provider-neutral HTTP facade for Memory Fabric.

    The API deliberately rejects DEVICE_ONLY and SECRET records at the remote
    boundary even if a future server-side provider could technically store
    them. Those privacy classes must never leave the originating device.
    """

    normalized_method = method.strip().upper()
    normalized_path = path or "/"

    if normalized_method == "GET" and normalized_path == "/v1/memory/health":
        return MemoryApiResult(
            status=200,
            payload={
                "providers": [
                    {
                        "provider_id": item.provider_id,
                        "status": item.status.value,
                        "readable": item.readable,
                        "writable": item.writable,
                        "checked_at": _iso(item.checked_at),
                        "details": dict(item.details),
                    }
                    for item in memory.health()
                ]
            },
        )

    if normalized_method != "POST":
        return MemoryApiResult(status=404, payload={"error": "not_found"})

    body = payload or {}

    if normalized_path == "/v1/memory/write":
        record = MemoryRecord.from_json(body)
        if not record.checksum_valid():
            return MemoryApiResult(
                status=400,
                payload={"error": "invalid_memory_checksum"},
            )
        if record.privacy_level in _REMOTE_FORBIDDEN:
            return MemoryApiResult(
                status=403,
                payload={"error": "privacy_not_remote"},
            )
        try:
            stored = memory.write(record)
        except MemoryPolicyError as exc:
            return MemoryApiResult(
                status=403,
                payload={"error": "memory_policy_rejected", "detail": str(exc)},
            )
        return MemoryApiResult(
            status=200,
            payload={"record": stored.to_json()},
        )

    if normalized_path == "/v1/memory/read":
        record_id = str(body.get("id", "")).strip()
        if not record_id:
            raise ValueError("memory id is required")
        record = memory.read(record_id)
        if record is None:
            return MemoryApiResult(
                status=404,
                payload={"error": "memory_not_found"},
            )
        if record.privacy_level in _REMOTE_FORBIDDEN:
            return MemoryApiResult(
                status=403,
                payload={"error": "privacy_not_remote"},
            )
        return MemoryApiResult(
            status=200,
            payload={"record": record.to_json()},
        )

    if normalized_path == "/v1/memory/search":
        query = _query_from_json(body)
        records = [
            record
            for record in memory.search(query)
            if record.privacy_level not in _REMOTE_FORBIDDEN
        ]
        return MemoryApiResult(
            status=200,
            payload={"records": [record.to_json() for record in records]},
        )

    if normalized_path == "/v1/memory/sync":
        reports = memory.sync()
        return MemoryApiResult(
            status=200,
            payload={
                "reports": [
                    {
                        "provider_id": item.provider_id,
                        "ok": item.ok,
                        "pulled": item.pulled,
                        "pushed": item.pushed,
                        "conflicts": item.conflicts,
                        "details": dict(item.details),
                    }
                    for item in reports
                ]
            },
        )

    if normalized_path == "/v1/memory/replicate":
        record_id = str(body.get("id", "")).strip()
        if not record_id:
            raise ValueError("memory id is required")
        source_provider_id = _optional_text(body.get("source_provider_id"))
        report = memory.replicate(
            record_id,
            source_provider_id=source_provider_id,
        )
        return MemoryApiResult(
            status=200,
            payload={
                "report": {
                    "record_id": report.record_id,
                    "attempted": list(report.attempted),
                    "succeeded": list(report.succeeded),
                    "failed": dict(report.failed),
                }
            },
        )

    return MemoryApiResult(status=404, payload={"error": "not_found"})


def _query_from_json(payload: dict[str, Any]) -> MemoryQuery:
    raw_types = payload.get("types", [])
    if not isinstance(raw_types, list):
        raise ValueError("memory query types must be an array")
    raw_tags = payload.get("tags", [])
    if not isinstance(raw_tags, list):
        raise ValueError("memory query tags must be an array")

    return MemoryQuery(
        namespace=_optional_text(payload.get("namespace")),
        types=tuple(MemoryType(str(item)) for item in raw_types),
        text=_optional_text(payload.get("text")),
        subject=_optional_text(payload.get("subject")),
        tags=tuple(str(item).strip() for item in raw_tags if str(item).strip()),
        project_id=_optional_text(payload.get("project_id")),
        user_id=_optional_text(payload.get("user_id")),
        agent_id=_optional_text(payload.get("agent_id")),
        conversation_id=_optional_text(payload.get("conversation_id")),
        updated_after=_optional_datetime(payload.get("updated_after")),
        updated_before=_optional_datetime(payload.get("updated_before")),
        include_expired=bool(payload.get("include_expired", False)),
        limit=int(payload.get("limit", 50)),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_datetime(value: object) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
