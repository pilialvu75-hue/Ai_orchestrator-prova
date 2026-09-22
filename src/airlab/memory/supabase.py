from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .model import (
    MemoryHealth,
    MemoryHealthStatus,
    MemoryQuery,
    MemoryRecord,
    PrivacyLevel,
    SyncReport,
)
from .provider import ProviderDescriptor


class SupabaseTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, object]: ...


class SupabaseRestTransport:
    """Minimal PostgREST transport with no supabase-py dependency.

    The API key may be a backend secret key or a publishable key. When using a
    publishable key, pass the signed-in user's JWT as authorization_token so RLS
    evaluates the user instead of the anonymous role.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        authorization_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        base_url = base_url.rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("Supabase base_url must be http(s)")
        if not api_key.strip():
            raise ValueError("Supabase api_key is required")
        self._base_url = base_url
        self._api_key = api_key.strip()
        self._authorization_token = (
            authorization_token.strip() if authorization_token else self._api_key
        )
        self._timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, object]:
        url = f"{self._base_url}{path}"
        if query:
            url += "?" + urlencode(query)

        request_headers = {
            "apikey": self._api_key,
            "Authorization": f"Bearer {self._authorization_token}",
            "Accept": "application/json",
        }
        request_headers.update(headers or {})

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
            request_headers["Content-Type"] = "application/json"

        request = Request(
            url,
            data=data,
            method=method.upper(),
            headers=request_headers,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return response.status, _decode_body(payload)
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            return exc.code, _decode_body(payload)
        except URLError as exc:
            raise ConnectionError(f"Supabase request failed: {exc.reason}") from exc


class SupabaseMemoryProvider:
    def __init__(
        self,
        *,
        transport: SupabaseTransport,
        table: str = "airlab_memory_records",
        provider_id: str = "supabase",
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("invalid Supabase table name")
        self._transport = transport
        self._table = table
        self._descriptor = ProviderDescriptor(
            provider_id=provider_id,
            location="cloud",
            allowed_privacy=frozenset(
                {
                    PrivacyLevel.PUBLIC,
                    PrivacyLevel.PROJECT,
                    PrivacyLevel.PRIVATE,
                }
            ),
            durable=True,
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    @property
    def _path(self) -> str:
        return f"/rest/v1/{self._table}"

    def write(self, record: MemoryRecord) -> MemoryRecord:
        if record.privacy_level not in self._descriptor.allowed_privacy:
            raise PermissionError(
                f"Supabase provider rejects privacy={record.privacy_level.value}"
            )

        current = self.read(record.id)
        if current is not None:
            if record.version < current.version:
                raise ValueError(
                    f"version regression for {record.id}: "
                    f"{record.version} < {current.version}"
                )
            if record.version == current.version:
                if record.checksum == current.checksum:
                    return current
                raise ValueError(
                    f"same-version checksum conflict for {record.id} v{record.version}"
                )

        status, payload = self._transport.request(
            "POST",
            self._path,
            query={"on_conflict": "id"},
            body=record.to_json(),
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        _require_success(status, payload)

        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return MemoryRecord.from_json(payload[0])
        return record

    def read(self, record_id: str) -> MemoryRecord | None:
        status, payload = self._transport.request(
            "GET",
            self._path,
            query={
                "select": "*",
                "id": f"eq.{record_id}",
                "limit": "1",
            },
        )
        _require_success(status, payload)
        if not isinstance(payload, list) or not payload:
            return None
        item = payload[0]
        if not isinstance(item, dict):
            raise ValueError("invalid Supabase memory row")
        return MemoryRecord.from_json(item)

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        params: dict[str, str] = {
            "select": "*",
            "order": "updated_at.desc",
            "limit": str(query.limit),
        }
        if query.namespace:
            params["namespace"] = f"eq.{query.namespace}"
        if query.types:
            if len(query.types) == 1:
                params["type"] = f"eq.{query.types[0].value}"
            else:
                values = ",".join(item.value for item in query.types)
                params["type"] = f"in.({values})"
        if query.subject:
            params["subject"] = f"eq.{query.subject}"
        if query.project_id:
            params["project_id"] = f"eq.{query.project_id}"
        if query.user_id:
            params["user_id"] = f"eq.{query.user_id}"
        if query.agent_id:
            params["agent_id"] = f"eq.{query.agent_id}"
        if query.conversation_id:
            params["conversation_id"] = f"eq.{query.conversation_id}"
        if query.updated_after:
            params["updated_at"] = f"gte.{_iso(query.updated_after)}"
        if query.updated_before:
            # PostgREST cannot represent two filters for one field in a mapping.
            # Apply the upper bound locally when both are supplied.
            if "updated_at" not in params:
                params["updated_at"] = f"lte.{_iso(query.updated_before)}"
        if query.text:
            term = _safe_search_term(query.text)
            params["or"] = f"(subject.ilike.*{term}*,content.ilike.*{term}*)"

        status, payload = self._transport.request("GET", self._path, query=params)
        _require_success(status, payload)
        if not isinstance(payload, list):
            raise ValueError("invalid Supabase search response")

        records = [
            MemoryRecord.from_json(item)
            for item in payload
            if isinstance(item, dict)
        ]
        if query.updated_before is not None:
            records = [
                record
                for record in records
                if record.updated_at <= query.updated_before
            ]
        if query.tags:
            required = set(query.tags)
            records = [
                record for record in records if required.issubset(set(record.tags))
            ]
        if not query.include_expired:
            records = [record for record in records if not record.is_expired()]
        return records[: query.limit]

    def sync(self) -> SyncReport:
        # Supabase is already a remote durable node. Cross-node propagation is
        # coordinated by MemoryFabric.replicate(), not hidden inside this adapter.
        return SyncReport(
            provider_id=self._descriptor.provider_id,
            ok=True,
            details={"mode": "remote_durable_node"},
        )

    def health(self) -> MemoryHealth:
        checked_at = datetime.now(timezone.utc)
        try:
            status, payload = self._transport.request(
                "GET",
                self._path,
                query={"select": "id", "limit": "1"},
            )
            if 200 <= status < 300:
                return MemoryHealth(
                    provider_id=self._descriptor.provider_id,
                    status=MemoryHealthStatus.HEALTHY,
                    readable=True,
                    writable=True,
                    checked_at=checked_at,
                    details={"http_status": status},
                )
            return MemoryHealth(
                provider_id=self._descriptor.provider_id,
                status=MemoryHealthStatus.DEGRADED,
                readable=False,
                writable=False,
                checked_at=checked_at,
                details={"http_status": status, "response": _safe_detail(payload)},
            )
        except Exception as exc:
            return MemoryHealth(
                provider_id=self._descriptor.provider_id,
                status=MemoryHealthStatus.UNAVAILABLE,
                readable=False,
                writable=False,
                checked_at=checked_at,
                details={"error": str(exc)},
            )


def _require_success(status: int, payload: object) -> None:
    if 200 <= status < 300:
        return
    raise RuntimeError(
        f"Supabase memory request failed with HTTP {status}: {_safe_detail(payload)}"
    )


def _decode_body(payload: str) -> object:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def _safe_detail(payload: object) -> object:
    if isinstance(payload, dict):
        return {
            key: value
            for key, value in payload.items()
            if key in {"code", "message", "details", "hint"}
        }
    if isinstance(payload, str):
        return payload[:300]
    return payload


def _safe_search_term(value: str) -> str:
    # Keep the PostgREST expression bounded and remove expression delimiters.
    return (
        value.strip()
        .replace("*", "")
        .replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")[:160]
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
