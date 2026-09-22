from __future__ import annotations

import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


class AirLabRequestHandler(BaseHTTPRequestHandler):
    service: BuilderService
    auth_token: str | None = None
    gateway: IntelligenceGateway | None = None
    memory: MemoryFabric | None = None

    def _authorized(self) -> bool:
        if not self.auth_token:
            return True
        return self.headers.get("Authorization") == f"Bearer {self.auth_token}"

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard_auth(self) -> bool:
        if self._authorized():
            return True
        self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def _read_json_object(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("invalid request size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard_auth():
            return
        if self.path.startswith("/v1/memory"):
            if self.memory is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "memory_fabric_unavailable"},
                )
                return
            try:
                result = dispatch_memory_request(
                    self.memory,
                    method="GET",
                    path=self.path,
                )
                self._write_json(result.status, result.payload)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if self.path == "/health":
            caps = self.service.capabilities()
            self._write_json(
                HTTPStatus.OK,
                {"status": "ok", "service": caps.service, "engine_id": caps.engine_id},
            )
            return
        if self.path == "/v1/capabilities":
            self._write_json(HTTPStatus.OK, asdict(self.service.capabilities()))
            return
        if self.path == "/v1/intelligence/capabilities":
            if self.gateway is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "intelligence_gateway_unavailable"},
                )
                return
            self._write_json(
                HTTPStatus.OK,
                {"capabilities": self.gateway.capabilities_snapshot()},
            )
            return
        if self.path == "/v1/intelligence/providers":
            if self.gateway is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "intelligence_gateway_unavailable"},
                )
                return
            self._write_json(
                HTTPStatus.OK,
                {"providers": self.gateway.providers_snapshot()},
            )
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard_auth():
            return
        if self.path.startswith("/v1/memory"):
            if self.memory is None:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "memory_fabric_unavailable"},
                )
                return
            try:
                result = dispatch_memory_request(
                    self.memory,
                    method="POST",
                    path=self.path,
                    payload=self._read_json_object(),
                )
                self._write_json(result.status, result.payload)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if self.path not in {"/v1/tasks", "/v1/chat/completions"}:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            payload = self._read_json_object()
            if self.path == "/v1/tasks":
                request = BuildRequest.from_json(payload)
                response = self.service.execute(request)
                self._write_json(HTTPStatus.OK, response.to_json())
                return
            if self.path == "/v1/chat/completions":
                if self.gateway is None:
                    self._write_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "intelligence_gateway_unavailable"},
                    )
                    return
                request = parse_chat_completion_request(payload)
                response = self.gateway.complete(request)
                self._write_json(
                    HTTPStatus.OK,
                    chat_completion_response(response),
                )
                return
        except GatewayUnavailable:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "intelligence_unavailable"},
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(
    service: BuilderService,
    *,
    host: str,
    port: int,
    auth_token: str | None,
    gateway: IntelligenceGateway | None = None,
    memory: MemoryFabric | None = None,
) -> ThreadingHTTPServer:
    """Build an AIrLab HTTP server without starting its blocking loop."""

    handler = type(
        "ConfiguredAirLabRequestHandler",
        (AirLabRequestHandler,),
        {
            "service": service,
            "auth_token": auth_token,
            "gateway": gateway,
            "memory": memory,
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    service: BuilderService,
    *,
    host: str,
    port: int,
    auth_token: str | None,
    gateway: IntelligenceGateway | None = None,
    memory: MemoryFabric | None = None,
) -> ThreadingHTTPServer:
    server = create_server(
        service,
        host=host,
        port=port,
        auth_token=auth_token,
        gateway=gateway,
        memory=memory,
    )
    server.serve_forever()
    return server
