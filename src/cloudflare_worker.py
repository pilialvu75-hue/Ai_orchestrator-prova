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
from airlab.intelligence.gateway import create_control_gateway
from airlab.service import BuilderService


_DIAGNOSTICS = MemoryDiagnostics()
_SERVICE = BuilderService(
    engine=MockBuilderEngine(),
    library=NullModuleLibrary(),
    researcher=NullResearcher(),
    diagnostics=_DIAGNOSTICS,
)
_GATEWAY = create_control_gateway(_DIAGNOSTICS)


class Default(WorkerEntrypoint):
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
        result = dispatch_cloudflare_request(
            _SERVICE,
            method=method,
            path=url.path,
            authorization=authorization,
            body=body,
            auth_token=str(auth_token) if auth_token is not None else None,
            gateway=_GATEWAY,
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
