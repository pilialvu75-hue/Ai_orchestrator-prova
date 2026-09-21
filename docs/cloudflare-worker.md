# AIrLab on Cloudflare Python Workers

This adapter exposes the already-defined AIrLab HTTP contract on Cloudflare without coupling the AIrLab domain/service layer to Cloudflare.

## Product choice

Use **Cloudflare Workers (Python Workers)** for the current AIrLab backend.

Do not use Pages as the primary backend runtime. AIrLab already has a Python Worker entrypoint and the Cloudflare runtime is the correct execution boundary for the private API. When the browser/PWA frontend is introduced, prefer **Workers Static Assets** (or a separate frontend only if there is a concrete reason to split it) rather than coupling the API to Pages.

The first Cloudflare deployment is intentionally a private staging deployment of the deterministic mock engine. It is a deployment/integration proof, not the production AI engine.

## Contract

The Worker exposes the same endpoints as the local loopback server:

- `GET /health`
- `GET /v1/capabilities`
- `POST /v1/tasks`

The active engine remains `MockBuilderEngine`. No real LLM, provider, Workers AI, NAS, GPU, or external hardware is enabled by this adapter.

## Security model

The Worker is fail-closed.

`AIRLAB_AUTH_TOKEN` MUST be configured as an encrypted Cloudflare Worker Secret. The Wrangler configuration declares it as a required secret, so deployment must fail if it has not been configured. If the binding is nevertheless absent at runtime, every request returns `503 service_unconfigured`. If the bearer token is missing or wrong, every request returns `401 unauthorized`.

The token MUST NOT be placed in:

- `wrangler.toml`;
- source control;
- Flutter Web assets;
- diagnostics;
- API responses.

Cloudflare Access should be placed in front of the Worker as an additional account-level barrier during development and stabilization. The Worker-side secret remains useful as defense in depth and for controlled service-to-service/native clients.

No permissive CORS headers are emitted by default. A browser client must therefore be integrated later through the intended private Web/backend boundary rather than receiving a reusable API secret.

## Wrangler / pywrangler

Cloudflare Python Workers use `pywrangler`, which wraps Wrangler and bundles Python dependencies for deployment.

Typical development commands are:

```text
uv sync --group dev
uv run pywrangler dev
```

For local development, put only local values in an ignored `.dev.vars` file:

```text
AIRLAB_AUTH_TOKEN="local-development-token"
```

The runtime entrypoint is `src/cloudflare_worker.py` and the Worker configuration is `wrangler.toml`.

The compatibility date is intentionally pinned to the date already covered by the repository's Worker smoke test. Update it only together with a successful Worker-runtime verification.

## First protected deployment

Authenticate Wrangler/pywrangler with the intended Cloudflare account, then configure the encrypted secret and deploy:

```text
uv run pywrangler secret put AIRLAB_AUTH_TOKEN
uv run pywrangler deploy
```

After deployment, protect the Worker with **Cloudflare Access** for all traffic while AIrLab remains private. The `workers.dev` hostname is appropriate for this staging proof; use a Custom Domain/route later for a production-grade endpoint.

## Deployment gate

Before considering the Cloudflare stage complete:

1. configure `AIRLAB_AUTH_TOKEN` as an encrypted Worker Secret;
2. deploy the Worker through the authorized Cloudflare account/tooling;
3. protect the Worker with Cloudflare Access while the project is private;
4. verify an unauthenticated request is blocked;
5. verify a bad bearer token is rejected;
6. verify `/health`, `/v1/capabilities`, and the deterministic mock `/v1/tasks` round trip;
7. inspect Worker invocation/error logs without logging prompt/task content;
8. keep the real repository write boundary inside Cantiere exactly as on native platforms.

No Cloudflare account identifiers, API tokens, auth tokens, or provider keys belong in this repository.
