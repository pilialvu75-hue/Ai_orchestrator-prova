from __future__ import annotations

import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import BuildRequest
from .service import BuilderService


@dataclass(frozen=True)
class CloudflareApiResult:
    status: int
    payload: dict[str, Any]


def dispatch_cloudflare_request(
    service: BuilderService,
    *,
    method: str,
    path: str,
    authorization: str | None,
    body: str | None,
    auth_token: str | None,
) -> CloudflareApiResult:
    """Map a Cloudflare Worker request onto the stable AIrLab HTTP contract.

    This function deliberately depends only on the Python standard library and
    AIrLab domain/service code. The Cloudflare runtime adapter remains a thin
    shell, while this dispatcher is fully testable in the normal Python 3.11 CI.

    Security is fail-closed: a deployed Worker without AIRLAB_AUTH_TOKEN must
    not accidentally expose the API publicly.
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
        return CloudflareApiResult(status=404, payload={"error": "not_found"})

    if normalized_method == "POST":
        if normalized_path != "/v1/tasks":
            return CloudflareApiResult(status=404, payload={"error": "not_found"})

        try:
            if body is None:
                raise ValueError("invalid request size")
            encoded = body.encode("utf-8")
            if not encoded or len(encoded) > 1_000_000:
                raise ValueError("invalid request size")

            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")

            request = BuildRequest.from_json(payload)
            response = service.execute(request)
            return CloudflareApiResult(status=200, payload=response.to_json())
        except (ValueError, json.JSONDecodeError) as exc:
            return CloudflareApiResult(
                status=400,
                payload={"error": str(exc)},
            )

    return CloudflareApiResult(status=404, payload={"error": "not_found"})
