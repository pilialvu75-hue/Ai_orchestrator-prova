# AIrLab Architecture V1

Status: **Architecture baseline / coordination source**
Baseline date: **2026-09-22**
AIrLab repository baseline: `pilialvu75-hue/Ai_orchestrator-prova@037a64bbfb948fd6992ab65e24017e91c1105291`
AI-Orchestrator baseline: `pilialvu75-hue/Ai-orchestrator-riserva@8e112c9bfdd9ff14efa460e33d6696882f93e3db`

This document defines the V1 architecture and the ownership boundaries between AIrLab and AI-Orchestrator. It is intentionally a coordination document: implementation belongs to the specialized workstreams unless a shared contract must be defined here.

## 1. Architecture principles

1. **AIrLab is an orchestrator, not a single model runtime.**
2. **Add, do not replace.** Every important capability must allow more than one provider or implementation.
3. **Capabilities are the stable contract; providers are replaceable adapters.**
4. **Cantiere owns project lifecycle.** Project, Task, Execution, checkpoint, review, validation, approval, apply and resume remain owned by AI-Orchestrator Cantiere.
5. **AIrLab owns capability execution.** It can plan, route, call tools/models/workers, produce staged operations and artifacts, and return evidence.
6. **No provider-specific requirements cross the public boundary unless strictly required.**
7. **Free-first and spend-safe.** V1 must run at 0 EUR/month by default. Paid resources are opt-in and accounted.
8. **Fail closed.** Missing credentials, invalid capability claims, unavailable providers, unsafe artifact operations and missing validation evidence must not silently degrade into an unsafe path.
9. **Shared-core first.** New abstractions should be reusable by AIrLab and AI-Orchestrator when practical.
10. **Observability without prompt leakage.** Diagnostics may contain technical metadata, timings and closed-vocabulary states, but not raw task/prompt text by default.

## 2. Verified baseline

### AIrLab already has

- Python 3.11 service foundation.
- Stable HTTP boundary: `GET /health`, `GET /v1/capabilities`, `POST /v1/tasks`.
- Extensible task families: `software.*`, `web.*`, `cad.*`, `manufacturing.*`.
- Generic input references: text, image, drawing, file, measurement, project.
- Artifact descriptors and safety rule separating editable CAD source from derived STL/G-code.
- `ModelEngine`, `ModuleLibraryPort`, `ResearcherPort`, `DiagnosticsPort`.
- Deterministic mock engine.
- Loopback HTTP integration tests.
- Private Cloudflare Python Worker adapter.
- Fail-closed Worker bearer-token authentication.
- Worker smoke workflow and standard Python CI.

### AI-Orchestrator already has

- Cantiere project/execution lifecycle and durable execution controller.
- AIrLab browser-safe client and typed contracts.
- Capability probing and task execution adapter.
- Controlled staging materialization.
- Staging-to-VirtualWorkspace promotion boundary.
- Reviewer/validation lifecycle integration.
- Module Library integration and offline snapshot verification.
- Researcher integration and current work on a fail-closed machine-policy gate.
- Diagnostics/RuntimeEventLog plus current PostHog observability work.
- Local and cloud inference infrastructure, provider-specific adapters and cloud-routing diagnostics.
- Durable/semantic memory foundations under active development.

### Important baseline constraint

AIrLab must **not** create a second project/execution state machine that competes with Cantiere. AIrLab may expose request/job state for a remote execution, but Cantiere remains the authority for the product lifecycle.

## 3. V1 component map

```text
User / UI / API client
        |
        v
AI-Orchestrator Cantiere
(Project / Task / Execution / Review / Validation / Apply / Resume)
        |
        | capability request
        v
+---------------------------------------------------------+
|                    AIRLAB CONTROL PLANE                 |
|                                                         |
|  Capability Registry ---- Provider Registry             |
|          |                    |                         |
|          +------> Model / Tool Router <-----+           |
|                         |                   |           |
|                  Resource Pool              |           |
|              quota / health / cost          |           |
|                         |                   |           |
|                  Policy / Accounting -------+           |
+-------------------------|-------------------------------+
                          |
                          v
+---------------------------------------------------------+
|                    EXECUTION PLANE                      |
|                                                         |
|  Task Dispatcher                                        |
|     |                                                   |
|     +--> LLM adapters                                   |
|     +--> Tool adapters                                  |
|     +--> Build workers                                  |
|     +--> Validation workers                             |
|     +--> Artifact workers                               |
+-------------------------|-------------------------------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
     Memory Fabric   Module Library     Researcher
          |               |                |
          +---------------+----------------+
                          |
                          v
                    Artifact Pipeline
                          |
                          v
                  controlled AIrLab result
                          |
                          v
             Cantiere staging / VirtualWorkspace
                          |
                          v
                Reviewer -> Validation -> Approval

Cross-cutting:
- Authentication / authorization
- Diagnostics / telemetry
- provider health
- retries / recovery
- provenance
- cost and quota accounting
```

## 4. Ownership boundaries

| Concern | Owner V1 | Rule |
|---|---|---|
| Project lifecycle | Cantiere | AIrLab never becomes authority for Project/Execution |
| Task classification | Shared contract, Cantiere initiates | AIrLab may refine capability requirements |
| Capability registry | Shared core candidate | Provider-neutral |
| Provider registry | Shared core candidate | Health/quota/cost metadata |
| Model/tool routing | Shared core candidate | Capability-driven |
| Memory abstraction | Shared core candidate | Multiple backends, policy-scoped |
| Module Library | Existing Library project | AIrLab consumes through port |
| Researcher | Existing Researcher project | AIrLab consumes evidence through port |
| Diagnostics | Existing Diagnostics project | AIrLab emits structured events |
| Artifact production | AIrLab execution plane | Must carry provenance and validation state |
| Staging / apply | Cantiere | AIrLab cannot write directly to real repository |
| User approval | Cantiere | Never bypassed |
| Cloudflare transport | AIrLab adapter | Not an architectural dependency |
| Build runners | Capability providers | GitHub Actions first, private runners later |

## 5. Capability Registry

The Capability Registry is the central provider-neutral vocabulary.

The platform has two capability layers so product orchestration and model routing do not become one overloaded namespace.

**Intelligence Gateway V1 capabilities** (used by model/provider routing):

- `chat.general`
- `reasoning.fast`
- `reasoning.deep`
- `coding.generate`
- `coding.review`
- `coding.debug`
- `architecture`
- `summarize`
- `classify`
- `long_context`
- `research`
- `vision`

**Platform/service capabilities** remain broader orchestration contracts:

- `research.search`
- `library.lookup`
- `memory.read`
- `memory.write`
- `artifact.store`
- `artifact.validate`
- `build.web`
- `build.android`
- `build.windows`
- `build.linux`
- `build.macos`
- `project.track`
- `analytics.event`

Historical coarse `llm.reasoning`, `llm.coding`, `llm.review` and `llm.summarize` names are superseded at the Intelligence Gateway boundary by the finer-grained V1 vocabulary above. They must not create a parallel registry.

A capability definition must be able to describe:

- capability id and version;
- accepted task/input kinds;
- output contract;
- required tools;
- latency class;
- privacy class;
- local/remote execution;
- cost class;
- health requirements;
- fallback policy;
- validation requirements.

Task families such as `web.build` remain user/product-level work categories. Capabilities describe the resources needed to execute them.

## 6. Provider / Resource Registry

A provider is an implementation of one or more capabilities. In the converged V1 architecture, `airlab.resources.ResourceRegistry` is the canonical source for schedulability, usage class, free-tier policy, live health and multi-metric quota. The Intelligence Gateway keeps a narrower execution registry for invocation metadata and short-lived circuit/rate state; it does not replace the Resource Pool.

Required provider metadata:

- `provider_id`;
- provider kind: model, tool, build worker, storage, research, memory;
- capabilities;
- endpoint/adapter id;
- health: healthy, degraded, unavailable, quota_exhausted, auth_required;
- cost mode: free, metered, paid;
- quota state;
- latency class;
- privacy/data-boundary flags;
- concurrency limit;
- last success/failure;
- cooldown/retry hints.

Provider keys and credentials remain in provider adapters or secret stores and never enter task payloads.

## 7. Intelligence Gateway / Router

The router receives a **capability requirement**, not a provider name.

Example:

```text
request: web.build
requirements:
  - llm.coding
  - llm.review
  - build.web
policy:
  free_first = true
  paid_allowed = false
  privacy = standard
```

Selection order:

1. filter providers that satisfy required capabilities;
2. remove unhealthy or policy-incompatible providers;
3. apply quota/cost constraints;
4. prefer reusable validated Library assets before generation;
5. choose provider based on declared policy and current health;
6. execute;
7. record technical outcome and resource usage;
8. on retryable failure, select another eligible provider;
9. return explicit failure when no eligible provider exists.

V1 must not use opaque "best model" logic. Routing decisions must be explainable from provider state and policy.

## 8. Memory Fabric

Memory Fabric is an abstraction, not one database.

Initial backend strategy:

- local durable memory from AI-Orchestrator;
- Supabase when the server-side track requires shared persistence;
- future NAS/home-server backend;
- optional provider-specific caches only as non-authoritative accelerators.

Core operations:

- `memory.read(scope, query, limits)`
- `memory.write(scope, record, provenance)`
- `memory.confirm(record)`
- `memory.invalidate(record)`

Memory classes:

- project state references;
- user-confirmed durable facts;
- reusable technical knowledge;
- execution evidence;
- provider health history;
- artifact metadata.

Raw model output is not automatically trusted durable memory.

## 9. Resource Pool

The Resource Pool presents free and paid resources as schedulable workers.

V1 resource categories:

- LLM/API providers;
- Cloudflare Workers/AI;
- GitHub Actions;
- local AI-Orchestrator devices;
- future NAS/home server;
- future dedicated runners.

Each resource exposes:

- supported capabilities;
- health;
- quota remaining;
- reset time when known;
- concurrency;
- estimated/actual cost;
- retry/cooldown state.

The pool must support **primary + secondary + fallback**, but not hard-code one global provider order for every capability.

## 10. Artifact Pipeline

Every produced artifact must carry enough metadata to answer:

- what task produced it;
- which provider/worker produced it;
- source inputs;
- source/editable/derived role;
- checksum or immutable identity where available;
- validation state;
- whether it is safe to present, stage or apply;
- cost/resource usage.

Initial product pipeline:

```text
Prompt
 -> plan
 -> reusable-module lookup
 -> research if required
 -> code/content generation
 -> artifact materialization
 -> build
 -> tests
 -> repair loop
 -> validation
 -> Cantiere review
 -> explicit approval
 -> final product
```

AIrLab returns results to controlled staging. Cantiere owns promotion to the real workspace.

## 11. Failure and recovery model

Failure classes:

- `provider_unavailable`
- `quota_exhausted`
- `authentication_required`
- `capability_unavailable`
- `retryable_remote_error`
- `non_retryable_request_error`
- `validation_failed`
- `artifact_invalid`
- `build_failed`
- `policy_blocked`

Rules:

- retries are bounded;
- fallback changes provider, not lifecycle ownership;
- duplicate billable execution must be prevented with idempotency/request identity;
- Cantiere checkpoint/resume remains authoritative;
- AIrLab remote jobs may expose correlation ids but cannot silently replay an already accepted operation;
- paid fallback is forbidden unless policy explicitly allows it.

## 12. Authentication and isolation

Current Worker bearer-token authentication is a staging baseline, not the final multi-user model.

V1 requirements before real users:

- authenticated principal;
- per-project authorization;
- secret isolation;
- provider credential isolation;
- artifact namespace isolation;
- request size limits;
- rate/quota enforcement;
- audit event for sensitive operations;
- no raw secret or prompt in diagnostics.

Multi-tenant billing and SLA are deferred until after the 0 EUR MVP works end to end.

## 13. Capability matrix

| Capability | Current implementation | V1 action |
|---|---|---|
| AIrLab HTTP transport | Implemented | Keep stable/additive |
| task-family contract | Implemented | Keep |
| deterministic engine | Implemented | Keep as control/test provider |
| Library lookup port | Implemented, null adapter in Worker | Connect existing Library |
| Researcher lookup port | Implemented, null adapter in Worker | Connect existing Researcher |
| Diagnostics port | Implemented | Bridge to existing Diagnostics |
| Cantiere staging/review | Implemented in AI-Orchestrator | Reuse, never duplicate |
| capability registry | Implemented in Intelligence Gateway V1 | Keep provider-neutral and mirror into Shared Core |
| provider/resource registry | Resource Pool V1 + merged Gateway V1 | `ResourceRegistry` is canonical scheduling state; Gateway keeps execution bindings/circuit state |
| model/tool router | Intelligence router implemented for model capabilities | Extend additively to tool/build capabilities |
| provider health/quota | Resource Pool V1 state manager + Memory Fabric persistence | Add authenticated provider probes; Gateway outcomes flow through the shared state manager |
| resource accounting | `UsageEvent` / `UsageLedger` + `MemoryUsageEventStore` implemented | Reuse canonical event contract; add monetary FinOps mapping later |
| durable Memory Fabric | Memory Fabric V1 merged | Reuse as provider/resource state and usage persistence; do not replace local memory |
| build.web worker | Not an AIrLab capability yet | P1 |
| build.android worker | Existing ecosystem/CI pieces | P1 after web |
| artifact store abstraction | Partial | P1 |
| multi-user auth | Not implemented | P2 |
| billing/SLA | Not implemented | P2 |

## 14. Provider matrix

| Provider/resource | Current role | State | V1 policy |
|---|---|---|---|
| deterministic mock engine | Contract/control provider | Active | Keep permanently for tests |
| Cloudflare Worker | Transport/runtime host | Active staging foundation | Adapter only |
| GitHub Actions | CI/build resource | Existing | First build-worker backend |
| AI-Orchestrator local runtime | Local inference | Existing in parent project | Shared adapter candidate |
| NVIDIA cloud models | Planned free-pool member | Not wired in AIrLab | 04 Resource Pool + 01 Router |
| OpenRouter | Planned multi-model source | Not wired in AIrLab | 04 + 01 |
| Cloudflare AI | Planned provider | Not wired | 04 + 01 |
| OpenAI / Claude paid APIs | Future premium resources | Deferred | Enable only after spend policy |
| NAS/home inference | Future local resource | Deferred | Add, never replace cloud/local |

## 15. Dependency map

```text
00 MASTER
  defines contracts / ownership / milestones
       |
       +--> 01 Intelligence Gateway & Model Router
       |      depends on Capability Registry + Provider Registry
       |
       +--> 02 Memory Fabric
       |      depends on shared scopes/provenance contracts
       |
       +--> 03 Durable Orchestrator
       |      integrates AIrLab execution with Cantiere lifecycle
       |      MUST NOT fork Project/Execution ownership
       |
       +--> 04 Free Resource Pool
              depends on Provider Registry + accounting schema

Existing shared services:
  Library ------> consumed through library.lookup
  Researcher ---> consumed through research.search/evidence
  Diagnostics --> consumes analytics/diagnostic events
  Cloud --------> provider adapters/resource state
  Platforms ----> build workers / artifact validation
```

## 16. Workstream assignments

### 00 MASTER / Architecture

Owns:
- capability vocabulary;
- provider-neutral contracts;
- dependency/order decisions;
- milestone definition;
- architecture decision log;
- convergence with AI-Orchestrator.

Does not own:
- all provider implementations;
- all memory backends;
- Cantiere execution code;
- Library/Researcher implementation.

### 01 Intelligence Gateway & Model Router

P0:
- Capability Registry contract;
- Provider Registry contract;
- routing policy;
- health-aware fallback;
- provider-independent execution request;
- explainable route decision.

### 02 Memory Fabric

P0:
- memory scope/provenance contract;
- adapter over existing AI-Orchestrator durable memory;
- backend-neutral interface;
- Supabase/NAS future adapters without replacing local memory.

### 03 Durable Orchestrator

P0:
- define exact AIrLab job/correlation boundary;
- idempotency;
- remote execution resume semantics;
- no duplicate lifecycle ownership;
- align with Cantiere parking/checkpoint/review.

### 04 Free Resource Pool

P0:
- resource descriptor;
- free-tier quota state;
- health/cooldown;
- concurrency;
- accounting events;
- free-first selection inputs for Router.

## 17. Priorities

### P0 — do now

1. Freeze Architecture V1 ownership boundaries.
2. Define Capability Registry schema.
3. Define Provider Registry + health/quota/accounting schema.
4. Define router request/decision contracts.
5. Define Memory Fabric contract and adapters to existing memory.
6. Define idempotency/correlation contract with Cantiere.
7. Connect existing Library, Researcher and Diagnostics through their ports.
8. Preserve deterministic mock as test oracle.
9. Add contract tests proving provider swap does not change Cantiere request semantics.

### P1 — immediately after P0 contracts

1. Real `web.build` path.
2. Free coding/reasoning provider adapters.
3. GitHub Actions build worker.
4. Artifact storage abstraction.
5. repair/test loop with bounded retries.
6. web-app end-to-end MVP.
7. simple-app MVP.
8. provider health dashboard/diagnostics.

### P2 — defer

- 3D/CAD real engines and slicers;
- multi-tenant billing;
- premium API default routing;
- dedicated GPU fleet;
- SLA;
- marketplace/general plugin ecosystem;
- broad autonomous task families before web/software reliability.

## 18. MVP 0 EUR milestone

MVP success is one repeatable, audited path:

```text
natural-language request
 -> Cantiere Project/Task
 -> AIrLab capability resolution
 -> Library reuse lookup
 -> Researcher evidence if required
 -> free coding/reasoning provider
 -> generated changes
 -> controlled staging
 -> build.web
 -> tests
 -> bounded repair
 -> Reviewer/validation
 -> explicit approval
 -> final downloadable/deployable web product
```

Acceptance criteria:

- no paid provider required;
- provider can be swapped without changing Cantiere lifecycle contract;
- provider outage produces explicit fallback or explicit failure;
- no direct AIrLab write to the real repository;
- no prompt text in default diagnostics;
- artifact provenance available;
- execution can recover without duplicate external work;
- deterministic mock path remains green.

## 19. Current risks

| Risk | Severity | Mitigation |
|---|---|---|
| AIrLab and Cantiere both evolve lifecycle state | Critical | Keep lifecycle ownership in Cantiere; AIrLab job ids are subordinate |
| Router becomes provider-specific | High | Capability-first contracts and adapter boundary |
| Free quotas fail unpredictably | High | Resource Pool health/quota/cooldown + explicit fallback |
| Duplicate paid/free remote calls on resume | High | Idempotency/correlation contract before real providers |
| Memory fragments across local/Supabase/NAS | High | Memory Fabric scopes/provenance + additive backends |
| Library/Researcher copied into AIrLab | High | Consume existing services through ports |
| Diagnostics leak task content | High | Closed-vocabulary metadata, existing privacy rule |
| stale PRs are mistaken for source of truth | Medium | main HEAD + merged contracts override older open branches |
| premature CAD/3D expansion | Medium | web/software MVP first |
| Cloudflare becomes hard dependency | Medium | keep it a transport/provider adapter |

## 20. Decision log

### D-001 — Cantiere remains lifecycle authority
Accepted. AIrLab does not own Product/Project/Execution approval/apply state.

### D-002 — capability-first routing
Accepted. Public orchestration asks for a capability, not a named provider.

### D-003 — additive providers/backends
Accepted. New providers and storage backends extend the system and do not replace existing ones by default.

### D-004 — deterministic mock remains permanent
Accepted. It is the provider-neutral contract oracle and CI fallback.

### D-005 — web/software before broad task families
Accepted. Real CAD/manufacturing execution waits until the MVP path is reliable.

### D-006 — free-first, paid opt-in
Accepted. No paid fallback without explicit policy and accounting.

### D-007 — shared core is contract-first
Accepted. Share schemas/interfaces/state vocabulary first; avoid premature monorepo or language-coupled extraction.

## 21. Immediate next architectural gate

The P0 Contract Pack is now split across merged shared cores. Gateway V1 provides `CapabilityDescriptor`, execution-provider bindings, `ProviderHealth`, `RouteRequest` and `RouteDecision`; Memory Fabric provides memory provenance/provider-neutral persistence; Free Resource Pool provides `ResourceDescriptor`, `ResourceStateSnapshot`, quota/health policy and `UsageEvent`.

The remaining cross-cutting contracts are:

1. `ResourceBudget` / future monetary FinOps policy beyond V1 virtual accounting;
2. `ExecutionCorrelation / idempotency key` for durable remote execution.

These contracts must be defined before wiring real LLM providers into AIrLab.

The contracts should be language-neutral enough to mirror between Python AIrLab and Dart AI-Orchestrator without forcing either repository to depend directly on the other's implementation.
