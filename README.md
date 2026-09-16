# AIrLab

AIrLab is the model-runtime service dedicated to **AI-Orchestrator Cantiere**.

The first milestone is deliberately hardware-independent. AIrLab starts with a deterministic mock builder so the API, routing, security boundary, Library/Researcher ports and Diagnostics contract can be proven before a real LLM is selected.

## Scope now

- Cantiere-only builder API
- deterministic mock engine
- model-engine abstraction
- Module Library port
- Researcher port
- privacy-safe Diagnostics port
- loopback-first HTTP service
- fail-closed authentication when exposed beyond localhost
- CI compile and unit tests

## Not included yet

- no real LLM
- no NAS/home server
- no GPU requirement
- no provider dependency
- no model download
- no PWA/browser runtime

## Run

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

## Integration direction

```text
AI-Orchestrator Cantiere
        |
        v
      AIrLab
        |
        +---- Module Library
        +---- Researcher
        +---- Diagnostics
        |
        v
  ModelEngine adapter
```

A future real model can run on the same machine, another computer, a home server or a remote endpoint without changing the Cantiere contract.

See `docs/ARCHITECTURE.md` and `docs/PROTOCOL.md`.
