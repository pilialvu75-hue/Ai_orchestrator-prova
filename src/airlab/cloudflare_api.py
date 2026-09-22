from __future__ import annotations

import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import BuildRequest
from .intelligence.gateway import GatewayUnavailable, IntelligenceGateway
from .intelligence.openai_compat import (
    chat_completion_response,
    parse_chat_completion_request,
)
from .memory import MemoryFabric
from .memory.api import dispatch_memory_request
from .service import BuilderService


@dataclass(frozen=True)
class CloudflareApiResult:
    status: int
    payload: dict[str, Any]


def _decode_json_body(body: str | None) -> dict[str, Any]:
    if body is None:
        raise ValueError("invalid request size")
    encoded = body.encode("utf-8")
    if not encoded or len(encoded) > 1_000_000:
        raise ValueError("invalid request size")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def dispatch_cloudflare_request(
    service: BuilderService,
    *,
    method: str,
    path: str,
    authorization: str | None,
    body: str | None,
    auth_token: str | None,
    gateway: IntelligenceGateway | None = None,
    memory: MemoryFabric | None = None,
) -> CloudflareApiResult:
    """Map a Cloudflare Worker request onto the stable AIrLab HTTP contract.

    Cloudflare remains a transport adapter. Intelligence routing is delegated to
    the provider-neutral gateway and never implemented in this module.
    """

    expected_token = (auth_token or "").strip()
    if not expected_token:
        return CloudflareApiResult(
            status=503,
            payload={"error": "service_unconfigured"},
        )

    expected_authorization = f"Bearer {expected_token}"
    supplied_authorization = authorization or ""
    if not hmac.compare_digest(supplied_authorization, expected_authorization):
        return CloudflareApiResult(
            status=401,
            payload={"error": "unauthorized"},
        )

    normalized_method = method.strip().upper()
    normalized_path = path or "/"

    if normalized_path.startswith("/v1/memory"):
        if memory is None:
            return CloudflareApiResult(
                status=503,
                payload={"error": "memory_fabric_unavailable"},
            )
        try:
            payload = (
                _decode_json_body(body)
                if normalized_method == "POST"
                else None
            )
            result = dispatch_memory_request(
                memory,
                method=normalized_method,
                path=normalized_path,
                payload=payload,
            )
            return CloudflareApiResult(
                status=result.status,
                payload=result.payload,
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return CloudflareApiResult(
                status=400,
                payload={"error": str(exc)},
            )

    if normalized_method == "GET":
        if normalized_path == "/health":
            capabilities = service.capabilities()
            return CloudflareApiResult(
                status=200,
                payload={
                    "status": "ok",
                    "service": capabilities.service,
                    "engine_id": capabilities.engine_id,
                },
            )
        if normalized_path == "/v1/capabilities":
            return CloudflareApiResult(
                status=200,
                payload=asdict(service.capabilities()),
            )
        if normalized_path == "/v1/intelligence/capabilities":
            if gateway is None:
                return CloudflareApiResult(
                    status=503,
                    payload={"error": "intelligence_gateway_unavailable"},
                )
            return CloudflareApiResult(
                status=200,
                payload={"capabilities": gateway.capabilities_snapshot()},
            )
        if normalized_path == "/v1/intelligence/providers":
            if gateway is None:
                return CloudflareApiResult(
                    status=503,
                    payload={"error": "intelligence_gateway_unavailable"},
                )
            return CloudflareApiResult(
                status=200,
                payload={"providers": gateway.providers_snapshot()},
            )
        return CloudflareApiResult(status=404, payload={"error": "not_found"})

    if normalized_method == "POST":
        if normalized_path not in {"/v1/tasks", "/v1/chat/completions"}:
            return CloudflareApiResult(status=404, payload={"error": "not_found"})
        try:
            payload = _decode_json_body(body)
            if normalized_path == "/v1/tasks":
                request = BuildRequest.from_json(payload)
                response = service.execute(request)
                return CloudflareApiResult(status=200, payload=response.to_json())
            if normalized_path == "/v1/chat/completions":
                if gateway is None:
                    return CloudflareApiResult(
                        status=503,
                        payload={"error": "intelligence_gateway_unavailable"},
                    )
                request = parse_chat_completion_request(payload)
                response = gateway.complete(request)
                return CloudflareApiResult(
                    status=200,
                    payload=chat_completion_response(response),
                )
        except GatewayUnavailable:
            return CloudflareApiResult(
                status=503,
                payload={"error": "intelligence_unavailable"},
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return CloudflareApiResult(
                status=400,
                payload={"error": str(exc)},
            )

    return CloudflareApiResult(status=404, payload={"error": "not_found"})
