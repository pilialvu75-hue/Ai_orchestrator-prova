from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class MemoryType(StrEnum):
    CONVERSATION = "conversation"
    PROJECT = "project"
    USER_PREFERENCE = "user_preference"
    KNOWLEDGE = "knowledge"
    LIBRARY_KNOWLEDGE = "library_knowledge"
    RESEARCH_KNOWLEDGE = "research_knowledge"
    EXECUTION_HISTORY = "execution_history"
    FAILURE_SOLUTION = "failure_solution"
    ARTIFACT_METADATA = "artifact_metadata"
    PROVIDER_RESOURCE_STATE = "provider_resource_state"
    DECISION_LOG = "decision_log"
    EPISODIC = "episodic"
    LONG_TERM_FACT = "long_term_fact"


class PrivacyLevel(StrEnum):
    PUBLIC = "public"
    PROJECT = "project"
    PRIVATE = "private"
    DEVICE_ONLY = "device_only"
    SECRET = "secret"


class NodeRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    READ_ONLY = "read_only"
    OFFLINE_CACHE = "offline_cache"


class MemoryHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    namespace: str
    type: MemoryType
    subject: str
    content: str
    structured_data: dict[str, Any]
    source: str
    confidence: float
    created_at: datetime
    updated_at: datetime
    version: int
    ttl: int | None
    replication_state: dict[str, str]
    privacy_level: PrivacyLevel
    checksum: str
    tags: tuple[str, ...] = ()
    project_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("memory id is required")
        if not self.namespace.strip():
            raise ValueError("memory namespace is required")
        if not self.subject.strip():
            raise ValueError("memory subject is required")
        if not self.source.strip():
            raise ValueError("memory source is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        if self.version < 1:
            raise ValueError("memory version must be >= 1")
        if self.ttl is not None and self.ttl < 0:
            raise ValueError("memory ttl must be >= 0")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    @classmethod
    def create(
        cls,
        *,
        namespace: str,
        type: MemoryType,
        subject: str,
        content: str,
        source: str,
        structured_data: dict[str, Any] | None = None,
        confidence: float = 1.0,
        ttl: int | None = None,
        privacy_level: PrivacyLevel = PrivacyLevel.PROJECT,
        tags: tuple[str, ...] = (),
        project_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        record_id: str | None = None,
    ) -> "MemoryRecord":
        now = datetime.now(timezone.utc)
        record = cls(
            id=record_id or str(uuid4()),
            namespace=namespace.strip(),
            type=type,
            subject=subject.strip(),
            content=content,
            structured_data=dict(structured_data or {}),
            source=source.strip(),
            confidence=confidence,
            created_at=now,
            updated_at=now,
            version=1,
            ttl=ttl,
            replication_state={},
            privacy_level=privacy_level,
            checksum="",
            tags=tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
            project_id=_clean_optional(project_id),
            user_id=_clean_optional(user_id),
            agent_id=_clean_optional(agent_id),
            conversation_id=_clean_optional(conversation_id),
        )
        return replace(record, checksum=record.compute_checksum())

    def next_version(
        self,
        *,
        content: str | None = None,
        structured_data: dict[str, Any] | None = None,
        source: str | None = None,
        confidence: float | None = None,
        replication_state: dict[str, str] | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> "MemoryRecord":
        record = replace(
            self,
            content=self.content if content is None else content,
            structured_data=(
                dict(self.structured_data)
                if structured_data is None
                else dict(structured_data)
            ),
            source=self.source if source is None else source.strip(),
            confidence=self.confidence if confidence is None else confidence,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
            replication_state=(
                dict(self.replication_state)
                if replication_state is None
                else dict(replication_state)
            ),
            tags=self.tags if tags is None else tuple(tags),
            checksum="",
        )
        return replace(record, checksum=record.compute_checksum())

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.ttl is None:
            return False
        reference = now or datetime.now(timezone.utc)
        return reference >= self.created_at + timedelta(seconds=self.ttl)

    def compute_checksum(self) -> str:
        payload = {
            "id": self.id,
            "namespace": self.namespace,
            "type": self.type.value,
            "subject": self.subject,
            "content": self.content,
            "structured_data": self.structured_data,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "version": self.version,
            "ttl": self.ttl,
            "privacy_level": self.privacy_level.value,
            "tags": list(self.tags),
            "project_id": self.project_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def checksum_valid(self) -> bool:
        return bool(self.checksum) and self.checksum == self.compute_checksum()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "type": self.type.value,
            "subject": self.subject,
            "content": self.content,
            "structured_data": dict(self.structured_data),
            "source": self.source,
            "confidence": self.confidence,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "version": self.version,
            "ttl": self.ttl,
            "replication_state": dict(self.replication_state),
            "privacy_level": self.privacy_level.value,
            "checksum": self.checksum,
            "tags": list(self.tags),
            "project_id": self.project_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "MemoryRecord":
        return cls(
            id=str(payload["id"]),
            namespace=str(payload["namespace"]),
            type=MemoryType(str(payload["type"])),
            subject=str(payload["subject"]),
            content=str(payload.get("content", "")),
            structured_data=dict(payload.get("structured_data") or {}),
            source=str(payload["source"]),
            confidence=float(payload.get("confidence", 1.0)),
            created_at=_parse_datetime(payload["created_at"]),
            updated_at=_parse_datetime(payload["updated_at"]),
            version=int(payload.get("version", 1)),
            ttl=(None if payload.get("ttl") is None else int(payload["ttl"])),
            replication_state=dict(payload.get("replication_state") or {}),
            privacy_level=PrivacyLevel(str(payload.get("privacy_level", "project"))),
            checksum=str(payload.get("checksum", "")),
            tags=tuple(str(tag) for tag in payload.get("tags") or ()),
            project_id=_clean_optional(payload.get("project_id")),
            user_id=_clean_optional(payload.get("user_id")),
            agent_id=_clean_optional(payload.get("agent_id")),
            conversation_id=_clean_optional(payload.get("conversation_id")),
        )


@dataclass(frozen=True)
class MemoryQuery:
    namespace: str | None = None
    types: tuple[MemoryType, ...] = ()
    text: str | None = None
    subject: str | None = None
    tags: tuple[str, ...] = ()
    project_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    conversation_id: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    include_expired: bool = False
    limit: int = 50

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 500:
            raise ValueError("memory query limit must be between 1 and 500")


@dataclass(frozen=True)
class MemoryHealth:
    provider_id: str
    status: MemoryHealthStatus
    readable: bool
    writable: bool
    checked_at: datetime
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncReport:
    provider_id: str
    ok: bool
    pulled: int = 0
    pushed: int = 0
    conflicts: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplicationReport:
    record_id: str
    attempted: tuple[str, ...]
    succeeded: tuple[str, ...]
    failed: dict[str, str]


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
