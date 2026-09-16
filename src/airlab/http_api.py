from __future__ import annotations

import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .contracts import BuildRequest
from .service import BuilderService


class AirLabRequestHandler(BaseHTTPRequestHandler):
    service: BuilderService
    auth_token: str | None = None

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

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard_auth():
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
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard_auth():
            return
        if self.path != "/v1/tasks":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            request = BuildRequest.from_json(payload)
            response = self.service.execute(request)
            self._write_json(HTTPStatus.OK, response.to_json())
        except (ValueError, json.JSONDecodeError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(
    service: BuilderService,
    *,
    host: str,
    port: int,
    auth_token: str | None,
) -> ThreadingHTTPServer:
    """Build an AIrLab HTTP server without starting its blocking loop.

    Production calls this through :func:`serve`. Tests and future embedding
    adapters can own the lifecycle explicitly, including binding to port 0 for
    an ephemeral loopback-only endpoint.
    """

    handler = type(
        "ConfiguredAirLabRequestHandler",
        (AirLabRequestHandler,),
        {"service": service, "auth_token": auth_token},
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(
    service: BuilderService,
    *,
    host: str,
    port: int,
    auth_token: str | None,
) -> ThreadingHTTPServer:
    server = create_server(
        service,
        host=host,
        port=port,
        auth_token=auth_token,
    )
    server.serve_forever()
    return server
