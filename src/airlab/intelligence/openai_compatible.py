from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Mapping, Protocol

from airlab.resources import ResourceHealth, ResourceStateSnapshot

from .contracts import GatewayRequest, ProviderOutput
from .gateway import ProviderExecutionError


@dataclass(frozen=True)
class JsonHttpResponse:
    status_code: int
    payload: dict[str, Any]
    headers: dict[str, str]


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse: ...


class HttpxJsonTransport:
    """Synchronous HTTP transport supported by Python Workers and CPython.

    Import httpx lazily so pure contract tests can run without importing a
    network client. Production packaging declares httpx explicitly.
    """

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        import httpx

        try:
            with httpx.Client(follow_redirects=False) as client:
                response = client.post(
                    url,
                    headers=dict(headers),
                    json=dict(payload),
                    timeout=timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError(
                "provider request timed out",
                kind="timeout",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError(
                "provider network request failed",
                kind="network",
                retryable=True,
            ) from exc

        try:
            decoded = response.json()
        except ValueError:
            decoded = {}
        if not isinstance(decoded, dict):
            decoded = {}

        return JsonHttpResponse(
            status_code=int(response.status_code),
            payload=decoded,
            headers={str(k).lower(): str(v) for k, v in response.headers.items()},
        )


class OpenAICompatibleProvider:
    """Provider-neutral adapter for OpenAI-compatible Chat Completions APIs."""

    def __init__(
        self,
        *,
        provider_id: str,
        endpoint: str,
        api_key_provider: Callable[[], str],
        transport: JsonHttpTransport | None = None,
        extra_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        normalized_id = provider_id.strip()
        normalized_endpoint = endpoint.strip()
        if not normalized_id:
            raise ValueError("provider_id is required")
        if not normalized_endpoint.startswith("https://"):
            raise ValueError("provider endpoint must use https")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

        self._provider_id = normalized_id
        self._endpoint = normalized_endpoint
        self._api_key_provider = api_key_provider
        self._transport = transport or HttpxJsonTransport()
        self._extra_headers = dict(extra_headers or {})
        self._timeout_seconds = float(timeout_seconds)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def complete(self, request: GatewayRequest, *, model: str) -> ProviderOutput:
        credential = self._api_key_provider().strip()
        if not credential:
            raise ProviderExecutionError(
                "provider credential is not configured",
                kind="authentication",
                retryable=True,
            )

        response = self._transport.post_json(
            self._endpoint,
            headers={
                "authorization": f"Bearer {credential}",
                "content-type": "application/json",
                **self._extra_headers,
            },
            payload={
                "model": model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": False,
            },
            timeout_seconds=self._timeout_seconds,
        )

        if response.status_code < 200 or response.status_code >= 300:
            raise _provider_error_for(response)

        text = _extract_text(response.payload)
        if not text:
            raise ProviderExecutionError(
                "provider returned an empty completion",
                kind="provider_error",
                retryable=True,
            )

        raw_model = response.payload.get("model")
        resolved_model = (
            raw_model.strip()
            if isinstance(raw_model, str) and raw_model.strip()
            else model
        )
        return ProviderOutput(
            text=text,
            model=resolved_model,
            usage=_extract_usage(response.payload),
        )


class OpenAICompatibleProbe:
    """Authenticated capability probe used before a remote resource is schedulable."""

    def __init__(
        self,
        *,
        resource_id: str,
        provider: OpenAICompatibleProvider,
        model: str,
    ) -> None:
        self._resource_id = resource_id
        self._provider = provider
        self._model = model

    @property
    def resource_id(self) -> str:
        return self._resource_id

    def probe(self) -> ResourceStateSnapshot:
        from .contracts import GatewayMessage, GatewayRequest

        started = monotonic()
        try:
            self._provider.complete(
                GatewayRequest(
                    capability="chat.general",
                    messages=(
                        GatewayMessage(
                            role="user",
                            content="Reply with OK.",
                        ),
                    ),
                    max_tokens=2,
                    temperature=0.0,
                ),
                model=self._model,
            )
        except ProviderExecutionError as exc:
            latency_ms = (monotonic() - started) * 1000.0
            return ResourceStateSnapshot(
                resource_id=self._resource_id,
                health=_resource_health_for_failure(exc.kind),
                checked_at=_utc_now(),
                availability=_availability_for_failure(exc.kind),
                quota_remaining={},
                cooldown_until=None,
                latency_ms=latency_ms,
            )

        latency_ms = (monotonic() - started) * 1000.0
        return ResourceStateSnapshot(
            resource_id=self._resource_id,
            health=ResourceHealth.HEALTHY,
            checked_at=_utc_now(),
            availability="api_reachable",
            quota_remaining={},
            latency_ms=latency_ms,
        )


def _provider_error_for(response: JsonHttpResponse) -> ProviderExecutionError:
    status = response.status_code
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    error_blob = response.payload.get("error")
    error_text = _safe_error_text(error_blob).lower()

    if status in {401, 403}:
        return ProviderExecutionError(
            f"provider authentication failed ({status})",
            kind="authentication",
            retryable=True,
        )
    if status == 408:
        return ProviderExecutionError(
            "provider request timed out",
            kind="timeout",
            retryable=True,
            retry_after_seconds=retry_after,
        )
    if status == 429:
        kind = (
            "quota"
            if any(token in error_text for token in ("quota", "credit", "balance"))
            else "rate_limit"
        )
        return ProviderExecutionError(
            f"provider capacity limit reached ({status})",
            kind=kind,
            retryable=True,
            retry_after_seconds=retry_after,
        )
    if status == 402:
        return ProviderExecutionError(
            "provider quota or credit exhausted",
            kind="quota",
            retryable=True,
            retry_after_seconds=retry_after,
        )
    if status >= 500:
        return ProviderExecutionError(
            f"provider unavailable ({status})",
            kind="provider_unavailable",
            retryable=True,
            retry_after_seconds=retry_after,
        )
    if 400 <= status < 500:
        return ProviderExecutionError(
            f"provider rejected request ({status})",
            kind="invalid_request",
            retryable=False,
        )
    return ProviderExecutionError(
        f"unexpected provider HTTP status ({status})",
        kind="provider_error",
        retryable=True,
    )


def _extract_text(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def _extract_usage(payload: Mapping[str, Any]) -> dict[str, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            result[key] = value
    return result


def _safe_error_text(value: Any) -> str:
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, dict):
        pieces: list[str] = []
        for key in ("code", "type", "message"):
            item = value.get(key)
            if isinstance(item, str):
                pieces.append(item[:128])
        return " ".join(pieces)
    return ""


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value.strip())
    except ValueError:
        return None
    return max(0.0, parsed)


def _resource_health_for_failure(kind: str) -> ResourceHealth:
    if kind == "rate_limit":
        return ResourceHealth.RATE_LIMITED
    if kind == "quota":
        return ResourceHealth.EXHAUSTED
    if kind in {"authentication", "network", "provider_unavailable"}:
        return ResourceHealth.DOWN
    return ResourceHealth.DEGRADED


def _availability_for_failure(kind: str) -> str:
    return {
        "authentication": "authentication_required",
        "rate_limit": "rate_limited",
        "quota": "quota_exhausted",
        "timeout": "timeout",
        "network": "network_unavailable",
        "provider_unavailable": "provider_unavailable",
        "invalid_request": "probe_rejected",
        "provider_error": "provider_error",
    }.get(kind, "provider_error")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
