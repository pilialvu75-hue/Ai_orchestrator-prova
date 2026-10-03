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

The active engine remains `MockBuilderEngine`. No real LLM, provider, Workers AI, NAS, GPU, or external hardware is required for the staging proof.

## Security model

The Worker is fail-closed.

`AIRLAB_AUTH_TOKEN` MUST be configured as an encrypted Cloudflare Worker Secret. The Wrangler configuration declares it as a required secret, so deployment must fail if it has not been configured. If the binding is nevertheless absent at runtime, every request returns `503 service_unconfigured`. If the bearer token is missing or wrong, every request returns `401 unauthorized`.

The token MUST NOT be placed in:

- `wrangler.toml`;
- source control;
- Flutter Web assets;
- diagnostics;
- API responses.

Cloudflare Access sits in front of the Worker as the outer account-level barrier during development and stabilization. The Worker-side secret remains useful as defense in depth and for controlled service-to-service/native clients.

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

## Guarded private deployment workflow

The repository includes `.github/workflows/cloudflare-private-deploy.yml` for the first private staging deployment.

The workflow is manual-only and requires the exact confirmation string:

```text
DEPLOY_PRIVATE_AIRLAB
```

Configure these values as GitHub **environment/repository secrets**, never as source-controlled variables:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `AIRLAB_AUTH_TOKEN`
- `CLOUDFLARE_ACCESS_EMAIL`

The Cloudflare API token used by this workflow must be scoped to the minimum permissions required for the deployment: Worker script deployment/read access plus **Access: Apps and Policies Write** for the private Access application.

The workflow deliberately prepares a hostname-level Access application for only:

```text
airlab-private-mock.<account-subdomain>.workers.dev
```

It does **not** enable account-wide Access and therefore must not change the privacy behavior of unrelated Workers.

For a new deployment it creates an owner-only Access rule for `CLOUDFLARE_ACCESS_EMAIL` before the Worker is uploaded. If an application already exists, the workflow refuses to deploy when it finds a bypass policy, an `everyone` rule, multiple matching Access applications, or a missing owner-only allow rule.

`AIRLAB_AUTH_TOKEN` is uploaded with `pywrangler deploy --secrets-file` from an ephemeral file that is removed before the job exits. The secret is never written to the repository or printed by the workflow.

After deployment, the job verifies that unauthenticated traffic remains fail-closed behind Cloudflare Access.

## Manual Wrangler path

For account-side troubleshooting outside GitHub Actions, authenticate Wrangler/pywrangler with the intended Cloudflare account, configure the encrypted secret and deploy:

```text
uv run pywrangler secret put AIRLAB_AUTH_TOKEN
uv run pywrangler deploy
```

Keep Cloudflare Access enabled for all AIrLab staging traffic. The `workers.dev` hostname is appropriate for this staging proof; use a Custom Domain/route later for a production-grade endpoint.

## Deployment gate

Before considering the Cloudflare stage complete:

1. configure `AIRLAB_AUTH_TOKEN` as an encrypted Worker Secret;
2. deploy the Worker through the authorized Cloudflare account/tooling;
3. protect the Worker with Cloudflare Access while the project is private;
4. verify an unauthenticated request is blocked;
5. verify a bad bearer token is rejected at the Worker boundary when testing through an authorized Access path;
6. verify `/health`, `/v1/capabilities`, and the deterministic mock `/v1/tasks` round trip remotely;
7. inspect Worker invocation/error logs without logging prompt/task content;
8. keep the real repository write boundary inside Cantiere exactly as on native platforms.

No Cloudflare account identifiers, API tokens, auth tokens, Access identities, or provider keys belong in this repository.
