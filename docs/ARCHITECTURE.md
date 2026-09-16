# AIrLab architecture v0.1

AIrLab is a builder-runtime service for AI-Orchestrator Cantiere. It is not a general Assistant and it does not own the Module Library, Researcher or Diagnostics projects.

## Initial topology

```text
AI-Orchestrator Cantiere
        |
        v
     AIrLab API
        |
        v
  BuilderService
   |    |    |
   |    |    +-- DiagnosticsPort
   |    +------- ResearcherPort
   +------------ ModuleLibraryPort
        |
        v
   ModelEngine
        |
        v
 deterministic mock
```

The mock engine is intentional. The first milestone proves the service contract and integration path without external hardware, model downloads or paid providers.

## Future adapters

A real model is introduced only after the foundation is stable. Model engines may later be local llama.cpp/Ollama/vLLM, browser-safe endpoints, a home inference node, or a cloud fallback. Cantiere must not need to know where the engine runs.

## Security baseline

- default bind is `127.0.0.1`;
- binding to a non-loopback address requires `AIRLAB_AUTH_TOKEN`;
- no provider keys are compiled into clients;
- diagnostics contain technical metadata only, never task/prompt text;
- model selection is an adapter concern, not a Cantiere contract.

## Next gates

1. Foundation contract and CI green.
2. Cantiere client adapter against the mock API.
3. Module Library and Researcher adapters.
4. Diagnostics transport adapter.
5. End-to-end build simulation.
6. Only then benchmark real coding models.
