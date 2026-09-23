from __future__ import annotations

import json
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import (
    MemoryDiagnostics,
    NullModuleLibrary,
    NullResearcher,
)
from airlab.cloudflare_api import dispatch_cloudflare_request
from airlab.intelligence.composition import create_environment_gateway
from airlab.service import BuilderService


_DIAGNOSTICS = MemoryDiagnostics()
_SERVICE = BuilderService(
    engine=MockBuilderEngine(),
    library=NullModuleLibrary(),
    researcher=NullResearcher(),
    diagnostics=_DIAGNOSTICS,
)
_PROVIDER_SECRET_NAMES = ("AIRLAB_NVIDIA_API_KEY",)


class Default(WorkerEntrypoint):
    _gateway = None

    def _gateway_for_request(self):
        if self._gateway is None:
            secrets = {
                name: str(getattr(self.env, name, "") or "")
                for name in _PROVIDER_SECRET_NAMES
            }
            self._gateway = create_environment_gateway(
                _DIAGNOSTICS,
                secrets=secrets,
            )
        return self._gateway
    async def fetch(self, request):
        url = urlparse(request.url)
        method = str(request.method).upper()
        authorization = request.headers.get("Authorization")

        body: str | None = None
        if method == "POST":
            body = str(await request.text())

        # AIRLAB_AUTH_TOKEN must be configured as a Worker Secret. It is never
        # committed to source/wrangler and never returned to callers.
        auth_token = getattr(self.env, "AIRLAB_AUTH_TOKEN", None)
        gateway = (
            self._gateway_for_request()
            if url.path.startswith("/v1/intelligence/")
            or url.path == "/v1/chat/completions"
            else None
        )
        result = dispatch_cloudflare_request(
            _SERVICE,
            method=method,
            path=url.path,
            authorization=authorization,
            body=body,
            auth_token=str(auth_token) if auth_token is not None else None,
            gateway=gateway,
        )

        return Response(
            json.dumps(result.payload, separators=(",", ":")),
            status=result.status,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
