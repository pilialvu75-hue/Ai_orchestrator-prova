# Free Resource Pool V1

Status: **P0 implementation / verified catalog baseline**  
Verification date: **2026-09-22**  
Repository: `pilialvu75-hue/Ai_orchestrator-prova`

## 1. Purpose

Free Resource Pool gives AIrLab, the Intelligence Gateway, Durable Orchestrator and
AI-Orchestrator one provider-neutral view of resources that may be used at zero
monetary cost.

It does **not** claim that a configured provider is currently reachable, that an
account has remaining quota, or that a free developer offer is valid for production.
Static provider facts and dynamic account/runtime state are deliberately separate.

Core rules:

- capability first, provider second;
- no global "best provider" order;
- free does not mean production/commercially permitted;
- unprobed resources start `UNKNOWN` and fail closed;
- paid fallback is never implicit;
- provider credentials never enter task payloads;
- Resource Pool chooses/records resources but never owns Project/Execution lifecycle;
- Cantiere remains lifecycle authority;
- Memory Fabric owns persistence for health history, quotas and accounting;
- providers/backends are additive and replaceable.

## 2. V1 contracts

Implemented in `src/airlab/resources/`:

- `ResourceDescriptor` — static provider/resource facts plus current projected state;
- `QuotaMetric` — named limit/remaining/reset metadata;
- `ResourceHealth` — HEALTHY, DEGRADED, RATE_LIMITED, EXHAUSTED, DOWN, DISABLED, UNKNOWN;
- `UsageClass` — PERSONAL, DEVELOPMENT, PROTOTYPING, COMMERCIAL, PRODUCTION;
- `ResourceRegistry` — capability/policy/quota/health filtering and capability-specific ordering;
- `UsageEvent` / `UsageLedger` — normalized virtual-cost accounting;
- `free_resource_pool_v1()` — verified initial static catalog.

Runtime health and remaining quota are intentionally not fabricated. An authenticated
provider adapter must update them before automatic selection.

## 3. Legacy Work Map — Resource Pool scope

| Component | Source | Real state | Decision |
|---|---|---|---|
| Cloud provider catalog | AI-Orchestrator `cloud_provider_catalog.dart` | Existing, used by parent runtime | REUSE classifications and adapters; do not duplicate provider calls |
| Cloud access classification | AI-Orchestrator `docs/cloud/point-1-5-access-classification.md` | Existing and current | REUSE fail-closed distinction between recurring free, developer/prototype, account-dependent and paid |
| Fixed provider priority lists | AI-Orchestrator cloud catalog | Compatibility-only legacy | SUPERSEDED for new routing by capability-specific resource priority + live state |
| AIrLab provider/resource registry | Architecture V1 | Previously missing | IMPLEMENTED here as P0 contract |
| Cantiere Project/Task/Execution | AI-Orchestrator | Existing; AIrLab integration merged | REUSE; Resource Pool must not create a second lifecycle |
| Diagnostics / RuntimeEventLog | AI-Orchestrator | Existing | REUSE as local source; Resource Pool emits closed-vocabulary resource/usage events later |
| PostHog bridge | AI-Orchestrator PR #543 | Open at verification time | DO NOT treat as merged source of truth |
| Memory Fabric | AIrLab branch `airlab-memory-fabric-v1` | Parallel active branch | DO NOT overlap; later persist quota/health/accounting through its contract |
| Intelligence Gateway branch | `feat/intelligence-gateway-v1` | Behind current main with no unique commits at verification | Router must consume Resource Pool contracts when rebuilt on current main |
| Cloudflare Worker adapter | AIrLab merged PRs #7/#9 | Implemented staging transport | REUSE as host/transport adapter, not hard dependency |
| Library / Researcher | AI-Orchestrator existing integrations | Existing | REUSE; Researcher may submit candidate resources, never auto-promote them |

## 4. Connected-tool verification

Connection state is distinct from registry membership.

| Tool/service | Verified connection state | Scheduling consequence |
|---|---|---|
| GitHub | Connector operational with repository read/write access | Repo/CI adapters can be implemented and live-probed |
| Supabase | Connector installed, but no accessible project was returned during this verification | Catalogued, but not schedulable until a project exists and health is proven |
| Hugging Face | Authenticated non-Pro account visible | Useful for model/dataset discovery; no free GPU compute is assumed from authentication alone |
| PostHog | Connector installed, but the AIrLab target project is not verified here | Keep remote analytics UNKNOWN; local Diagnostics remains valid fallback |
| Linear | Plugin available but not installed | Catalogued as optional project-tracking resource; GitHub Issues remains replacement |
| Cloudflare | Worker code exists in repository; no account connector is available in this chat | Runtime health stays UNKNOWN until deployment/account probe |
| Groq / NVIDIA / Mistral / OpenRouter | No ChatGPT account connector available | Project API adapters must authenticate and probe account quota/health |

## 5. Initial provider matrix

The table records documented free access. It is not a live account balance.

| Resource | Capabilities | Free-policy class | Documented V1 quota/limit | Production/commercial policy |
|---|---|---|---|---|
| OpenRouter Free Pool | LLM general/reasoning/coding/review | recurring free pool, model-dependent | Free plan documents 50 requests/day | selected model terms must be checked |
| Groq Free | LLM general/reasoning/coding/review | account-dependent free | qwen/qwen3.8-27b documented at 30 RPM, 1000 RPD, 8K TPM, 200K TPD | do not assume from provider name alone |
| NVIDIA NIM developer | LLM reasoning/coding/review/general | development/prototyping | no static remaining quota claimed | production requires the appropriate NVIDIA production entitlement |
| Mistral Free mode | LLM general/reasoning/coding/review | account-dependent free mode | $10/month included API credit documented | hard-stop before pay-as-you-go |
| GitHub Actions standard | build.*, workflow.ci, artifact.build | free according to repository/plan rules | public standard runners free; GitHub Free private allowance 2000 min/month + 500 MB artifacts | repository/plan terms apply; larger runners excluded |
| Supabase Free | memory.*, Postgres, artifact storage, realtime | free project tier | 500 MB DB, 1 GB file storage, 5 GB egress/month, 500k Edge Function invocations/month | project/account terms apply |
| Cloudflare Workers Free | hosting.web, serverless, gateway | recurring free limits | 100k requests/day, 10 ms CPU/request, 128 MB memory | provider terms apply |
| Inngest Hobby | durable workflow, task queue, scheduling | free hobby tier | 50k executions/month, 500k events/month, 5 concurrent steps, 100k queue depth | provider terms apply; quota exhaustion must park/fallback |
| PostHog Free | analytics, remote diagnostics, flags | free usage thresholds | 1M analytics events/month, 5k replays/month, 1M feature-flag requests/month | telemetry/privacy policy still applies |
| Linear Free | project.track | free workspace tier | 250 issues, 2 teams, API/webhooks, 10 MB uploads | optional; not currently installed |
| GitHub Issues | project.track | repository service | live API rate limits, no fake static remaining quota | repository/plan terms apply |

## 6. Capability map and fallback intent

Examples of capability-specific routing:

```text
llm.reasoning
  -> NVIDIA NIM developer (only DEV/PROTOTYPING when health + account policy allow)
  -> Groq Free
  -> OpenRouter Free Pool
  -> Mistral Free mode

llm.coding
  -> NVIDIA NIM developer (DEV/PROTOTYPING)
  -> Groq Free
  -> OpenRouter Free Pool
  -> Mistral Free mode

build.android / build.web / build.windows / build.linux / build.macos
  -> GitHub Actions standard
  -> future local/NAS runner

memory.read / memory.write
  -> Memory Fabric chooses local/shared backend
  -> Supabase is one optional node, never the memory architecture

workflow.durable
  -> existing Cantiere durable controller remains lifecycle authority
  -> Inngest may become a remote workflow execution adapter

project.track
  -> GitHub Issues
  -> Linear Free

diagnostics.remote
  -> PostHog when explicitly configured and healthy
  -> local Diagnostics always remains valid
```

The numeric `priority` values in the catalog are **inputs**, not an absolute ranking.
The Router must combine capability, usage class, health, remaining quota, latency,
privacy and policy before choosing a resource.

## 7. Health and quota lifecycle

Static catalog load:

```text
resource -> UNKNOWN
```

Authenticated/runtime probe:

```text
UNKNOWN
  -> HEALTHY
  -> DEGRADED
  -> RATE_LIMITED
  -> EXHAUSTED
  -> DOWN

operator/policy -> DISABLED
```

`RATE_LIMITED`, `EXHAUSTED`, `DOWN` and `DISABLED` are not selectable.
`UNKNOWN` is also non-selectable by default. This prevents a documented free tier
from being mistaken for an immediately usable account resource.

Quota `remaining` is runtime state. The static catalog may contain documented
limits, but does not invent remaining balances.

## 8. Virtual accounting

Zero-euro execution still records consumption.

Example:

```text
task=build-demo
  3 llm_calls        resource=openrouter_free_pool
  7 ci_minutes       resource=github_actions_standard
  120 storage_mb     resource=artifact_backend
  1 deployment       resource=cloudflare_workers_free
```

`virtual_cost` is a normalized internal unit in V1. It is intentionally separate
from real currency. Later FinOps policy can map usage metrics to monetary prices
without changing task/resource contracts.

The in-memory `UsageLedger` is only the contract/reference implementation.
Durable storage belongs to Memory Fabric.

## 9. Intelligence Gateway integration contract

The Router should not receive `provider=nvidia` from application code.

It receives, conceptually:

```text
capability=llm.coding
usage_class=DEVELOPMENT
require_free=true
privacy=standard
```

Then:

1. probe/update provider state;
2. ask Resource Registry for eligible candidates;
3. combine Resource Pool state with Router quality/latency policy;
4. execute one candidate with an idempotency/correlation key;
5. record a UsageEvent and technical outcome;
6. mark rate-limit/quota/health state when learned;
7. retry through the next eligible resource only for retryable failures;
8. never cross into paid or production-incompatible access silently.

The Resource Pool therefore supplies scheduling facts; the Intelligence Gateway owns
model/tool route decisions.

## 10. Durable Orchestrator integration contract

Resource Pool does not wait on CI, own project state, or create another state machine.

For a remote operation it supplies:

- chosen resource id;
- capability;
- quota/health snapshot;
- cooldown/reset hints;
- usage/accounting event.

Durable Orchestrator/Cantiere supplies:

- project/task/execution identity;
- idempotency key;
- RUN/WATCH/PARK/resume behavior;
- retry scheduling;
- checkpoint and approval lifecycle.

This preserves the existing Cantiere authority while making external resources
replaceable.

## 11. Researcher candidate pipeline

Researcher may discover a resource or changed quota, but discovery does not mutate
the official catalog directly.

```text
DISCOVERED
 -> CANDIDATE
 -> TERMS_CHECKED
 -> QUOTA_CHECKED
 -> CAPABILITY_TESTED
 -> VALIDATED
 -> REGISTRY
```

A rejected/deprecated candidate remains in evidence/history so the same unsuitable
resource is not repeatedly rediscovered.

Candidate validation must record documentation URL, terms URL, verification date,
usage class, quotas, fallback and evidence of capability/health probing.

## 12. Legacy Decisions / Migration Log

| Previous decision/implementation | Current status | Decision |
|---|---|---|
| AI-Orchestrator CloudProviderCatalog is canonical for parent cloud providers | Current and useful | CONFIRMED / reuse through adapter |
| Only recurring free tier is automatically spend-safe by classification alone | Current parent policy | CONFIRMED |
| Groq can be treated as universally spend-safe merely because a Free plan exists | Conflicts with current parent access classification | SUPERSEDED; account-dependent |
| NVIDIA developer endpoints can serve production by default | Conflicts with documented developer/prototyping scope | REJECTED |
| One global provider priority list decides every task | Compatibility legacy only | SUPERSEDED by capability-specific + live-state selection |
| Supabase is the memory system | Architecture V1 says Memory Fabric is multi-backend | SUPERSEDED; Supabase is only one node |
| Cloudflare is a required AIrLab dependency | Architecture V1 says adapter only | REJECTED |
| PostHog open PR can be assumed merged | GitHub says PR #543 remains open | REJECTED until merged |
| AIrLab may create a second durable Project/Execution machine | Conflicts with Architecture V1 | REJECTED |
| Resource usage at €0 needs no accounting | Commercial-readiness requirement | SUPERSEDED; virtual accounting required |

## 13. Next implementation gates

P0 continuation:

1. add provider-state probe/adapters that update health and remaining quota;
2. persist ResourceSnapshot/UsageEvent via Memory Fabric once that contract merges;
3. expose the same schema to AI-Orchestrator through a Dart/shared-contract adapter;
4. let the Intelligence Gateway consume `eligible()` rather than fixed provider names;
5. add closed-vocabulary diagnostics for selection, fallback, rate limit and exhaustion;
6. add the Researcher candidate-validation inbox;
7. add a read-only resource-status API only after Router/health contracts stabilize.

No real provider is automatically enabled merely by appearing in this catalog.
