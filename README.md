# AIrLab

AIrLab is the evolving orchestration platform for **AI-Orchestrator Cantiere**.

The repository already contains a deliberately hardware-independent builder/runtime foundation. Architecture V1 keeps that working base and grows it into a provider-neutral orchestrator able to coordinate models, tools, memory, Library, Researcher, builds, validation and artifacts without depending on one provider.

## Current implemented scope

- stable Cantiere-facing builder API;
- deterministic mock engine kept as a permanent contract/CI provider;
- model-engine abstraction;
- Module Library port;
- Researcher port;
- privacy-safe Diagnostics port;
- loopback-first HTTP service;
- private Cloudflare Python Worker adapter;
- fail-closed authentication when exposed remotely;
- extensible task families: `software.*`, `web.*`, `cad.*`, `manufacturing.*`;
- compile, unit/integration and Worker smoke CI.

The real multi-provider Intelligence Gateway, Memory Fabric, Durable Orchestrator correlation layer and Free Resource Pool are the next P0 architecture workstreams. Existing AI-Orchestrator components are reused/generalized rather than duplicated.

## Run the current local foundation

```bash
PYTHONPATH=src python -m airlab.main
```

Default address: `http://127.0.0.1:8788`.

Health:

```bash
curl http://127.0.0.1:8788/health
```

Mock task:

```bash
curl -X POST http://127.0.0.1:8788/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Create a simple notes app","mode":"plan","target":"web"}'
```

## Architecture

Start with:

- `docs/AIRLAB_ARCHITECTURE_V1.md` — current component map, ownership, priorities and MVP.
- `docs/LEGACY_WORK_MAP.md` — verified reuse/migration map across AIrLab and Ai-orchestrator-riserva.
- `docs/ARCHITECTURE.md` — implemented runtime foundation and link to V1.
- `docs/PROTOCOL.md` — current transport contract.
- `docs/TASK_FAMILIES.md` — task-family and artifact rules.

Core principle: **request capabilities, not named providers**. A future model can run locally, on another computer/NAS, through a free cloud route or a paid provider without changing the Cantiere lifecycle contract.
