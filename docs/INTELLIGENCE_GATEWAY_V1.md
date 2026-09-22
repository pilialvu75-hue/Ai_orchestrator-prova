# Intelligence Gateway V1

Status: **merged V1 + Resource Pool convergence hardening**

Baseline:
- AIrLab Architecture V1 main after PR #12: `f3d52d2c91c437e437e12872030495dd719d2ed6`
- AI-Orchestrator main audited: `8e112c9bfdd9ff14efa460e33d6696882f93e3db`
- Architecture / Legacy Work Map: PR #12

## Purpose

The Intelligence Gateway is the provider-neutral inference boundary shared by AIrLab and, later, AI-Orchestrator online mode.

Application code requests a capability. It does not select NVIDIA, OpenRouter, Cloudflare, OpenAI, Claude, Mistral or another provider.

## V1 capability vocabulary

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

Capability descriptors carry minimum context, preferred/fallback model hints, latency ceiling, commercial-use policy, free-only policy and privacy requirements.

## Provider / Resource registry boundary

`airlab.resources.ResourceRegistry` is the canonical scheduling source for real providers: capability class, usage class, free-tier eligibility, live health and multi-metric quota. Gateway `ProviderRegistry` is deliberately narrower: invocation metadata plus short-lived execution/circuit state. `ResourcePoolBridge` maps the fine-grained Gateway capability vocabulary onto Resource Pool capability classes and makes the Resource Pool eligibility decision authoritative before Gateway quality/latency scoring.

Gateway execution descriptors carry:

- provider id, endpoint/adapter and model;
- capabilities and context window;
- rate/quota metadata;
- availability and observed health;
- latency and error metadata;
- usage-rights text;
- allowed environments: personal / development / production / commercial;
- commercial-use flag;
- cost and free-access classification;
- priority, quality score and privacy class.

Credentials never enter the routing contract.

## Routing

The router:

1. matches the requested capability;
2. rejects unavailable/cooldown providers;
3. checks context capacity;
4. enforces environment and commercial-use policy;
5. enforces privacy;
6. enforces free-only / paid-allowed spend policy;
7. enforces quota and capability latency ceilings;
8. scores remaining candidates using free-first, quality, health, latency, historical error rate, quota and explicit priority;
9. returns an explainable ordered route.

The scoring deliberately reuses semantics already proven in AI-Orchestrator's `CloudProviderCatalog` and `CloudRuntimeProvider`, but does not copy their Flutter/runtime ownership into AIrLab.

## Health, cooldown and circuit breaker

The Gateway execution registry tracks requests, failures, consecutive failures, observed latency, last failure kind and a short-lived requests-per-minute/circuit window. Canonical real-provider health/quota belongs to Resource Pool. Gateway outcomes are applied through `ResourcePoolStateManager`, so a configured `MemoryResourceStateStore` persists health, latency and cooldown observations through Memory Fabric.

Initial V1 cooldowns mirror the parent Cloud behavior where applicable:

- rate limit: 120 seconds;
- quota: 900 seconds;
- temporary network/provider failure: 20 seconds;
- generic circuit breaker after three consecutive failures: 30 seconds.

These are policy constants, not provider-specific hard-coding.

### Execution cooldown convergence

The Gateway computes short-lived circuit/rate cooldowns. The remaining cooldown is projected
into the canonical Resource Pool instead of starting a second independent timer. Resource
Pool keeps `RATE_LIMITED` and `DOWN` non-selectable until the deadline and then reopens
them as `DEGRADED` for controlled retry. `EXHAUSTED` stays blocked until fresh provider
quota evidence arrives.

## Fallback and diagnostics

Each execution records structured technical events:

- `intelligence_route_decided`
- `intelligence_route_rejected`
- `intelligence_provider_failed`
- `intelligence_fallback`
- `intelligence_provider_succeeded`
- `intelligence_provider_skipped`
- `intelligence_usage_persistence_failed`

Raw prompt text is not emitted. Resource usage is represented by the shared `UsageEvent` contract; Gateway can write both the in-memory reference ledger and a durable `MemoryUsageEventStore` without changing the routing API. Durable usage persistence is best-effort: a memory/storage outage emits `intelligence_usage_persistence_failed` and does not invalidate a successful model response.

The minimum V1 proof is covered by tests: provider A is selected, fails with a retryable timeout, provider B is used, a valid response is returned, and route/fallback events are recorded.

## Stable API

`POST /v1/chat/completions` is OpenAI-shaped but capability-driven.

Example request:

```json
{
  "capability": "coding.review",
  "messages": [
    {"role": "user", "content": "Review this change"}
  ],
  "environment": "development",
  "free_first": true,
  "free_only": true,
  "paid_allowed": false
}
```

The optional client `model` field is accepted for compatibility but does not select a provider or model.

The response reports `model: airlab-gateway` and does not expose the selected provider. Provider/model selection remains internal diagnostics data.

Additional authenticated inspection endpoints:

- `GET /v1/intelligence/capabilities`
- `GET /v1/intelligence/providers`

## Control provider

V1 wires a deterministic `airlab-control` provider only as a contract oracle for local/CI/staging execution. It is explicitly marked `contract-test-only`, development/personal only, free, non-commercial and local-only privacy.

It must not be confused with a production LLM.

## Legacy decisions / migration delta

Confirmed and reused:

- Cantiere remains Project/Task/Execution/review/approval/apply owner.
- Existing AIrLab HTTP and Cloudflare adapters remain transports.
- Existing `DiagnosticsPort` remains the event sink contract.
- AI-Orchestrator free-first/access classes, health scoring and failover are generalized rather than duplicated.
- The existing parent Cloud catalog remains authoritative for the mobile app until a shared-core adapter is introduced.

Not introduced:

- no second project lifecycle;
- no second Library or Researcher;
- no provider credentials in request payloads;
- no hard-coded global provider order;
- no automatic commercial use of development/free-prototype endpoints.

## Next migration ring

1. add authenticated provider probes/adapters that update canonical `ResourceStateSnapshot` values;
2. wire the first real free provider through a `ProviderBinding` without changing the public API;
3. ingest provider-reported quota and `Retry-After` into Resource Pool state rather than inventing Gateway-only quota fields;
4. expose the Gateway to AI-Orchestrator ONLINE mode while preserving Local llama.cpp OFFLINE mode;
5. add consensus/multi-model execution only for capabilities that require it.
