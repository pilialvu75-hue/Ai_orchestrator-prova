# AIrLab Legacy Work Map

Status: **historical baseline / migration coordination**
Baseline date: **2026-09-22**
AIrLab main: `037a64bbfb948fd6992ab65e24017e91c1105291`
AI-Orchestrator main: `8e112c9bfdd9ff14efa460e33d6696882f93e3db`

This map records what already exists before new architecture work is created. GitHub `main` is authoritative; historical chats are useful only when consistent with the current repositories.

## Status vocabulary

- **COMPLETE** — merged and present on current main.
- **PARTIAL** — useful implementation exists but is not yet the final shared/general capability.
- **OPEN** — active PR/issue remains.
- **REUSE** — existing component should be consumed or generalized, not reimplemented.
- **MIGRATE** — move behind a shared/provider-neutral contract.
- **OBSOLETE** — historical branch/approach superseded by current main.
- **VERIFY_RUNTIME** — code exists but real environment/device/provider evidence is still required.

## Legacy Work Map

| Component | Origin / repository | GitHub evidence | Real state | Reuse / migration action | Dependencies |
|---|---|---|---|---|---|
| AIrLab platform foundation | AIrLab/Web work; `Ai_orchestrator-prova` | PR #1, main | COMPLETE | REUSE as service/control-plane base | none |
| Task families and artifact contracts | AIrLab/Web | PR #1; `docs/TASK_FAMILIES.md` | COMPLETE | REUSE; grow only after validators/workers exist | Capability Registry |
| Loopback HTTP contract | AIrLab/Web | PR #3, main | COMPLETE | REUSE; keep transport stable/additive | auth, BuilderService |
| Cloudflare Python Worker adapter | Web/Cloudflare | PR #7 + #9, main | COMPLETE code; deployment separate | REUSE as transport/runtime adapter, never hard dependency | secret/config/deploy |
| Worker deployment readiness | Web/Cloudflare | PR #9; Worker smoke green | COMPLETE code / VERIFY_RUNTIME deployment | keep fail-closed auth and observability | Cloudflare account |
| `ModelEngine` abstraction | AIrLab foundation | `src/airlab/ports.py` | COMPLETE but narrow | MIGRATE/generalize into capability-based Intelligence Gateway; keep compatibility adapter | Capability/Provider Registry |
| Library port | AIrLab foundation | `ModuleLibraryPort` | COMPLETE contract, null runtime adapter | REUSE contract; connect real existing Library rather than copy it | Library service |
| Researcher port | AIrLab foundation | `ResearcherPort` | COMPLETE contract, null runtime adapter | REUSE contract; connect real Researcher evidence | Researcher |
| Diagnostics port | AIrLab foundation | `DiagnosticsPort` | COMPLETE contract, in-memory adapter | REUSE; bridge to canonical Diagnostics event vocabulary | Diagnostics |
| Cantiere → AIrLab task executor | Cantiere/AIrLab integration | PR #425 merged | COMPLETE | REUSE; do not create parallel executor | Cantiere guard, AIrLab transport |
| Controlled AIrLab staging | Cantiere | PR #448 merged | COMPLETE | REUSE; preserve no-direct-repository-write invariant | file scope, staging root |
| AIrLab staging → VirtualWorkspace | Cantiere | PR #546 merged; supersedes stale #453/#518/#521 lines | COMPLETE | REUSE current main only; older variants OBSOLETE | staging + VirtualWorkspace |
| Opt-in AIrLab capability composition | Cantiere | PR #547 merged | COMPLETE | REUSE; evolve provider selection behind shared capability contract | allocator/guard/dispatcher |
| AIrLab Reviewer/validation bridge | Cantiere | PR #548 merged | COMPLETE | REUSE; this is the canonical validation path | Reviewer + validation |
| Explicit AIrLab production runner | AIrLab issue #11 | open issue | OPEN | Next Cantiere-side integration ring; must consume existing controller, not fork it | #548 + production controller |
| Neutral Cantiere opening / explicit project restore | Cantiere 2.1 | PR #541 merged | COMPLETE | REUSE lifecycle behavior | project catalog/checkpoints |
| Project identity collision fix | Cantiere 2.1 | PR #544 merged | COMPLETE | REUSE | persistent project state |
| Parking resumable executions | Cantiere 2.1 | PR #545 | OPEN, CI green on head | Converge/rebase before merge; required by Durable Orchestrator semantics | current main lifecycle |
| Persistent checkpoint/recovery store | Cantiere | current main code | COMPLETE foundation | REUSE as lifecycle authority | project/execution identity |
| Researcher dispatch intake | Researcher/Cantiere | PR #535 merged | COMPLETE | REUSE | authenticated dispatch |
| Researcher contract materialization | Researcher/Cantiere | PR #536 merged | COMPLETE | REUSE | intake |
| Researcher → isolated project plan | Researcher/Cantiere | PR #537 merged | COMPLETE | REUSE | Workshop plan contracts |
| Researcher authoritative workspace session | Researcher/Cantiere | PR #538 merged | COMPLETE | REUSE | WorkshopEngine |
| Researcher validation lifecycle | Researcher/Cantiere | PR #539/#540 merged | COMPLETE | REUSE; stable Library stays isolated | Reviewer/validation |
| Researcher machine-policy gate | Researcher/Cantiere | PR #542 | OPEN; one Windows run cancelled, other major CI green | Converge after current-main compatibility check | #535–#540 |
| Module Library UI/status integration | Library | current main `features/module_library` | COMPLETE/ongoing | REUSE canonical Library as source of certified availability | Library data |
| Durable memory records/store | Memory work | current main `core/memory/assistant_durable_memory*` | COMPLETE foundation | REUSE as local backend candidate for Memory Fabric | SQLite/persistence |
| Application-facing durable memory service | Memory work | PR #522 | OPEN | Converge; do not invent a second confirmed/candidate memory service | durable store |
| Conversation/semantic memory | Assistant memory | current main `ConversationMemoryService`, semantic index | PARTIAL/shared candidate | Adapter behind Memory Fabric, keep Assistant behavior stable | embeddings/index |
| Cloud provider catalog | Cloud work | current main `cloud_provider_catalog.dart` | COMPLETE domain-specific catalog | MIGRATE concepts into generic Provider Registry; do not discard existing cloud catalog | routing/settings |
| Free-first cloud classification | Cloud work | current main + `docs/cloud/point-1-5-access-classification.md` | COMPLETE foundation | REUSE spend-safety semantics in Resource Pool | cost/access policy |
| OpenRouter free pool integration | Cloud | current main provider catalog/tests | COMPLETE in parent project | REUSE provider adapter/state when AIrLab Router is ready | provider registry |
| NVIDIA/Mistral free/account-dependent routes | Cloud | current cloud catalog/work | PARTIAL/VERIFY_RUNTIME | add through Resource Pool adapters, not hard-coded routing | quota/auth/health |
| Cloud routing bootstrap/runtime provider | Cloud | current main | COMPLETE parent implementation | REUSE patterns; extract provider-neutral pieces only | provider catalog/settings |
| Local model runtime / llama.cpp | Assistant | current main | COMPLETE parent capability, runtime validation ongoing | expose later as provider adapter; do not move runtime ownership prematurely | local runtime |
| Runtime model-selection fix | Assistant | PR #531 | OPEN, CI failed on current head | Do not depend on this branch until repaired; architecture remains provider-neutral | runtime tests |
| Diagnostics local event log | Diagnostics | current main | COMPLETE | REUSE as authoritative local technical log | runtime events |
| PostHog privacy-safe bridge | Diagnostics | PR #543 | OPEN; Android/Windows/Linux/macOS CI green | Candidate optional remote telemetry adapter; local Diagnostics remains authority | telemetry consent/config |
| GitHub Actions build capacity | platform/CI tracks | multiple workflows | COMPLETE infrastructure | First build-worker backend; wrap as `build.*` capability | artifact handoff |
| Windows/Linux/macOS/Android platform builds | platform chats | parent repo workflows | PARTIAL/ongoing per platform | consume as build workers, do not make platform branches architectural dependencies | CI health |
| Web/PWA public product layer | Web/AIrLab | planning + Cloudflare foundation | PARTIAL | implement after P0 contract pack and web-build worker | auth/router/artifacts |
| CAD/manufacturing real engines | AIrLab task-family design | contracts only | DEFERRED | keep schemas; real kernels/slicers are P2 after software/web MVP | tool/provider registry |
| Supabase shared persistence | plugin/project direction | external service connected | PARTIAL/not AIrLab core | future Memory/Project/Artifact backend adapter; additive only | schema/auth |
| NAS/home node | architecture direction | no current production adapter | DEFERRED | future provider/storage/build backend; never replace local/cloud | network/health |
| Cost/accounting core | multiple discussions | no generic AIrLab implementation | MISSING | P0 shared `UsageEvent` + ResourceBudget contract | Provider Registry |
| Generic Capability Registry | master architecture | no canonical implementation | MISSING | P0, contract-first | task taxonomy |
| Generic Provider Registry | master architecture | cloud-specific catalog exists | PARTIAL | P0 generalization/adapters | Capability Registry |
| General Model/Tool Router | master architecture | domain-specific routing exists | PARTIAL | P0 capability-driven router, preserve existing adapters | Provider Registry |
| Durable Orchestrator boundary | master architecture | Cantiere lifecycle exists; remote job contract missing | PARTIAL | define subordinate job correlation/idempotency only | Cantiere lifecycle |

## Superseded / obsolete lines

The following are historical inputs, not code sources to revive directly:

- old AIrLab staging PRs #453, #518 and #521 after the current-main rebuild landed in #546;
- any architecture that gives AIrLab direct repository write/apply authority;
- any plan that creates a second Project/Execution lifecycle beside Cantiere;
- provider-specific orchestration contracts such as "use NVIDIA" at the public planning boundary;
- single-backend memory plans that replace local memory with Supabase/NAS;
- paid or account-dependent provider fallback without explicit spend policy.

## Legacy Decisions / Migration Log

| Decision | Previous state | Current status | Migration decision |
|---|---|---|---|
| AIrLab is only a model runtime | Initial v0.1 wording | MODIFIED | AIrLab becomes a general orchestrator/control plane while preserving the existing runtime service |
| Cantiere owns project lifecycle | Established in production architecture | CONFIRMED | Keep Project/Task/Execution/review/approval/apply authority in Cantiere |
| AIrLab can mutate repositories directly | Never accepted in safe path | REJECTED | All generated mutations remain staging/VirtualWorkspace until explicit Cantiere approval |
| One provider can be the architecture | Historical experimentation used individual providers | SUPERSEDED | Capability-first, multi-provider registry + fallback |
| Cloudflare is the AIrLab backend | Web staging direction | MODIFIED | Cloudflare is one transport/runtime adapter, not a dependency of the core |
| Library/Researcher should be copied into AIrLab | Ports existed but no copy required | REJECTED | Existing projects remain authoritative and are connected through adapters |
| Memory = one database | Earlier local/server discussions | SUPERSEDED | Memory Fabric with local + Supabase + future NAS adapters |
| free-first cloud routing | Parent Cloud work | CONFIRMED | Promote semantics into Resource Pool/accounting contracts |
| deterministic mock is temporary | Initial foundation implication | MODIFIED | Keep permanently as contract oracle and CI provider |
| real CAD/3D immediately | Early product ambition | DEFERRED | web/software MVP first; retain contracts only |
| raw telemetry to remote service | Not required | REJECTED | local Diagnostics authority + privacy-safe optional telemetry |
| automatic Researcher apply | Not accepted | REJECTED | Researcher remains isolated/candidate-only through validation gates |

## Immediate convergence blockers

1. **P0 shared contracts do not yet exist**: capability, provider, route decision, usage/accounting, memory provenance and execution correlation.
2. **AIrLab Worker still uses `NullModuleLibrary` and `NullResearcher`**: real adapters are not wired.
3. **No generic provider-health/quota Resource Pool exists in AIrLab**.
4. **No generic accounting event contract exists**.
5. **Cantiere parking PR #545 is still open** and must converge with the advanced main before Durable Orchestrator semantics are considered stable.
6. **PostHog #543, Researcher policy #542 and memory service #522 are parallel open work**, so Shared Core extraction must not bypass their canonical contracts.
7. **A6 issue #11 is the next AIrLab/Cantiere production integration step**, but it must remain opt-in and reuse the existing production controller.

## Migration order

1. Freeze Architecture V1 and this Legacy Work Map.
2. Create the P0 Contract Pack without changing existing runtime behavior.
3. Adapt existing CloudProviderCatalog/free-first semantics into the generic Provider/Resource contracts.
4. Adapt existing durable memory into Memory Fabric.
5. Define Cantiere ↔ AIrLab execution correlation/idempotency.
6. Connect Library/Researcher/Diagnostics real adapters.
7. Complete A6 production-runner integration.
8. Add first real free provider through Resource Pool + Router.
9. Add `build.web` worker and complete the 0 EUR web MVP.
10. Only after the web path is repeatable, widen to simple apps and later CAD/3D.
