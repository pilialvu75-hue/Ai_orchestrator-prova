# AIrLab architecture

The current architectural source of truth is **[AIrLab Architecture V1](AIRLAB_ARCHITECTURE_V1.md)**.

The original v0.1 runtime architecture below remains important because it describes the implementation already present on `main`. It is now a **foundation layer**, not the complete product vision.

## Implemented foundation (historical v0.1)

AIrLab began as a hardware-independent builder-runtime service for AI-Orchestrator Cantiere.

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

This foundation is still valid and must be reused. The deterministic mock remains the contract oracle for CI while real providers are added behind provider-neutral capabilities.

## Architecture V1 direction

AIrLab is evolving into an **orchestrator/control plane**, not a single model runtime. The stable public concepts are capabilities and lifecycle contracts; model, tool, build, storage and research providers remain replaceable adapters.

Key rules:

- **add, do not replace** providers/backends;
- Cantiere remains authoritative for Project/Task/Execution/review/validation/approval/apply;
- AIrLab owns capability execution and returns controlled results/evidence;
- Library, Researcher and Diagnostics remain existing authoritative services consumed through ports;
- model/tool routing is capability-first, not provider-first;
- free-first/spend-safe policy is explicit;
- no provider keys or raw prompts belong in public task/diagnostic payloads;
- Cloudflare is one transport/runtime adapter, not an architectural dependency.

See:

- [AIRLAB_ARCHITECTURE_V1.md](AIRLAB_ARCHITECTURE_V1.md)
- [LEGACY_WORK_MAP.md](LEGACY_WORK_MAP.md)
- [TASK_FAMILIES.md](TASK_FAMILIES.md)
- [PROTOCOL.md](PROTOCOL.md)
