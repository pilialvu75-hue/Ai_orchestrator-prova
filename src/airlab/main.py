from __future__ import annotations

import os
from ipaddress import ip_address

from airlab.adapters.mock_engine import MockBuilderEngine
from airlab.adapters.null_integrations import MemoryDiagnostics, NullModuleLibrary, NullResearcher
from airlab.http_api import serve
from airlab.service import BuilderService


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    host = os.getenv("AIRLAB_HOST", "127.0.0.1")
    port = int(os.getenv("AIRLAB_PORT", "8788"))
    token = os.getenv("AIRLAB_AUTH_TOKEN") or None
    if not _is_loopback(host) and not token:
        raise SystemExit(
            "AIRLAB_AUTH_TOKEN is required when AIRLAB_HOST is not loopback"
        )
    service = BuilderService(
        engine=MockBuilderEngine(),
        library=NullModuleLibrary(),
        researcher=NullResearcher(),
        diagnostics=MemoryDiagnostics(),
    )
    serve(service, host=host, port=port, auth_token=token)


if __name__ == "__main__":
    main()
