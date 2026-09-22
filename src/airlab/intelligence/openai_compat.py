from __future__ import annotations

import time
from typing import Any

from .contracts import GatewayMessage, GatewayRequest, RoutePolicy
from .gateway import GatewayResponse


_ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
_ALLOWED_ENVIRONMENTS = {"personal", "development", "production", "commercial"}
_ALLOWED_PRIVACY = {"standard", "no_training", "local_only"}


def parse_chat_completion_request(payload: dict[str, Any]) -> GatewayRequest:
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError("messages must be a non-empty array")

    messages: list[GatewayMessage] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            raise ValueError("each message must be an object")
        role = str(raw.get("role", "")).strip().lower()
        content = raw.get("content")
        if role not in _ALLOWED_ROLES:
            raise ValueError("unsupported message role")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")
        messages.append(GatewayMessage(role=role, content=content))

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    capability = str(
        payload.get("capability") or metadata.get("capability") or "chat.general"
    ).strip()
    if not capability:
        raise ValueError("capability is required")

    environment = str(payload.get("environment", "development")).strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise ValueError("unsupported environment")

    privacy = str(payload.get("privacy", "standard")).strip().lower()
    if privacy not in _ALLOWED_PRIVACY:
        raise ValueError("unsupported privacy policy")

    max_tokens = int(payload.get("max_tokens", 512))
    if max_tokens <= 0 or max_tokens > 65_536:
        raise ValueError("max_tokens out of range")

    temperature = float(payload.get("temperature", 0.2))
    if temperature < 0.0 or temperature > 2.0:
        raise ValueError("temperature out of range")

    required_context_tokens = int(payload.get("required_context_tokens", 0))
    if required_context_tokens < 0:
        raise ValueError("required_context_tokens must be >= 0")

    complexity = float(payload.get("task_complexity", 0.5))
    if complexity < 0.0 or complexity > 1.0:
        raise ValueError("task_complexity must be between 0 and 1")

    paid_allowed = bool(payload.get("paid_allowed", False))
    free_only = bool(payload.get("free_only", not paid_allowed))
    free_first = bool(payload.get("free_first", True))

    return GatewayRequest(
        capability=capability,
        messages=tuple(messages),
        max_tokens=max_tokens,
        temperature=temperature,
        required_context_tokens=required_context_tokens,
        task_complexity=complexity,
        policy=RoutePolicy(
            environment=environment,  # type: ignore[arg-type]
            free_first=free_first,
            free_only=free_only,
            paid_allowed=paid_allowed,
            privacy=privacy,  # type: ignore[arg-type]
        ),
        metadata=dict(metadata),
    )


def chat_completion_response(response: GatewayResponse) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{response.request_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "airlab-gateway",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.text},
                "finish_reason": "stop",
            }
        ],
        "usage": response.usage,
        "airlab": {
            "request_id": response.request_id,
            "capability": response.capability,
            "attempts": len(response.attempts),
        },
    }
