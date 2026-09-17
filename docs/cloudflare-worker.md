# AIrLab on Cloudflare Python Workers

This adapter exists to expose the already-defined AIrLab HTTP contract on Cloudflare without coupling the AIrLab domain/service layer to Cloudflare.

## Contract

The Worker exposes the same endpoints as the local loopback server:

- `GET /health`
- `GET /v1/capabilities`
- `POST /v1/tasks`

The active engine remains `MockBuilderEngine`. No real LLM, provider, Workers AI, NAS, GPU, or external hardware is enabled by this adapter.

## Security model

The Worker is fail-closed.

`AIRLAB_AUTH_TOKEN` MUST be configured as an encrypted Cloudflare Worker Secret. If the secret is absent, every request returns `503 service_unconfigured`. If the bearer token is missing or wrong, every request returns `401 unauthorized`.

The token MUST NOT be placed in:

- `wrangler.toml`;
- source control;
- Flutter Web assets;
- diagnostics;
- API responses.

Cloudflare Access should be placed in front of the Worker as an additional account-level barrier during development and stabilization. The Worker-side secret remains useful as defense in depth and for controlled service-to-service/native clients.

No permissive CORS headers are emitted by default. A browser client must therefore be integrated later through the intended private Web/backend boundary rather than receiving a reusable API secret.

## Local Cloudflare-runtime verification

Cloudflare Python Workers use `pywrangler`. The project declares `workers-py` only as a development dependency.

Typical development commands are:

```text
uv sync --group dev
uv run pywrangler dev
```

The runtime entrypoint is `src/cloudflare_worker.py` and the Worker configuration is `wrangler.toml`.

## Deployment gate

Before deployment:

1. configure `AIRLAB_AUTH_TOKEN` as a Worker Secret;
2. deploy the Worker through the authorized Cloudflare account/tooling;
3. protect the Worker with Cloudflare Access while the project is private;
4. verify unauthorized requests are rejected;
5. verify `/health`, `/v1/capabilities`, and the deterministic mock `/v1/tasks` round trip;
6. keep the real repository write boundary inside Cantiere exactly as on native platforms.

No Cloudflare account identifiers, tokens, or secrets belong in this repository.
