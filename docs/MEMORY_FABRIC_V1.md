# AIrLab Memory Fabric V1

Status: implementation branch `airlab-memory-fabric-v1`  
Baseline date: 2026-09-22

## Goal

Applications call one stable facade:

- `memory.write()`
- `memory.read()`
- `memory.search()`
- `memory.sync()`
- `memory.health()`
- `memory.replicate()`

They do not depend on Supabase, NAS, SQLite, Cloudflare or a model provider.

The governing rule is **add nodes, do not replace them**.

## Audit result

GitHub remains the source of truth.

### Reusable parent implementation

`Ai-orchestrator-riserva` already contains:

- `core/memory/memory_provider.dart`: legacy conversation/context provider. Useful, but its contract is narrower than the canonical Memory Fabric contract.
- `core/memory/assistant_durable_memory.dart` and store: bounded durable facts/state with candidate/confirmed semantics.
- `ConversationMemoryService` + `RollingContextBuilder`: current Assistant conversation/context pipeline.
- SQLite project memory domain/data layers.
- `SyncManager` + CRDT/HLC local-first synchronization.
- Cantiere persistent checkpoints and execution journals.
- Library persistence and Researcher/Cantiere lifecycle integrations.

Open parent work that must not be duplicated:

- PR #522: application-facing durable memory service.
- PR #526: bounded confirmed-memory injection into Assistant chat.
- PR #545: resumable Cantiere parking semantics.

### AIrLab baseline

`Ai_orchestrator-prova` already has stable ports for model, Library, Researcher and Diagnostics, but no durable Memory Fabric implementation on main before this branch.

### Supabase state

The connected Supabase integration currently exposes no project. Therefore the code/schema can be prepared, but a real database migration cannot yet be applied or verified against a project.

This is a deployment blocker only, not an architecture blocker.

## Canonical model

`MemoryRecord` includes:

- id
- namespace
- type
- subject
- content
- structured_data
- source
- confidence
- created_at / updated_at
- version
- ttl
- replication_state
- privacy_level
- checksum
- tags
- optional project/user/agent/conversation scope identifiers

Memory types currently cover:

1. conversation
2. project
3. user preference
4. knowledge
5. library knowledge
6. research knowledge
7. execution history
8. failure/solution
9. artifact metadata
10. provider/resource state
11. decision log
12. episodic
13. long-term fact

## Ownership boundary

Memory Fabric **does not own the Cantiere lifecycle**.

Cantiere remains authoritative for Project, Task, Execution, checkpoint, review, validation, approval, apply and resume.

`ProjectMemoryService` stores a durable projection of:

- original request
- requirements
- decisions
- plan
- tasks
- attempts
- errors
- fixes
- CI evidence
- artifacts
- tests
- status
- completion criteria
- last error
- next step

This allows restart/recovery without creating a second state machine.

## Node model

Every provider is registered as:

- PRIMARY
- SECONDARY
- READ_ONLY
- OFFLINE_CACHE

Each node declares which privacy classes it accepts.

The V1 Supabase provider accepts:

- PUBLIC
- PROJECT
- PRIVATE

It rejects by policy:

- DEVICE_ONLY
- SECRET

Future local/NAS providers can accept those classes without changing application code.

## Failure model

Writes are attempted across all eligible writable nodes. A failed primary does not prevent a healthy secondary/offline node from accepting the write.

Reads walk the ordered nodes and skip:

- unavailable nodes
- expired records
- records with invalid checksums

Search merges replicas by logical id and keeps the newest version.

Replication is explicit and policy filtered.

## Versioning and conflicts

V1 uses monotonic integer versions plus SHA-256 checksums.

The Supabase reference schema rejects:

- version regression
- same-version records with a different checksum

Same-version writes with the same checksum are idempotent and may update replication metadata.

The existing AI-Orchestrator CRDT/HLC implementation remains valuable for the future local/NAS adapter. It should be adapted rather than replaced.

## Supabase security boundary

The reference Supabase table has RLS enabled and removes `anon`/`authenticated` table access for V1.

The trusted server adapter uses a Supabase backend secret key. That key must never be placed in Android, desktop, browser or other shipped clients.

A later authenticated client-facing adapter can use publishable keys + user JWT + explicit ownership RLS, without changing the Memory Fabric API.

## Migration map

| Existing component | Status | Memory Fabric action |
|---|---|---|
| Dart `MemoryProvider` conversation API | legacy/narrow | keep stable; wrap/rename during parent convergence |
| durable memory store | reusable | local durable adapter candidate |
| ConversationMemoryService | reusable | conversation-memory adapter/client |
| SQLite ProjectMemory | reusable but old shape | map to canonical project projection |
| SyncManager CRDT/HLC | reusable | local/NAS sync engine candidate |
| Cantiere checkpoint store | authoritative | consume as source; never replace |
| Library store | authoritative domain store | publish selected knowledge through memory adapter |
| Researcher evidence | authoritative evidence source | publish validated research memory |
| Supabase | new shared node | additive cloud provider |
| NAS | future node | additive LAN provider |
| local DB/cache | future node | additive device/offline provider |

## First end-to-end acceptance test

The test suite writes a `ProjectMemorySnapshot` through a Supabase-compatible provider, destroys/recreates the provider/fabric/service objects, then retrieves the project and verifies that these survive:

- original request
- status
- tasks
- last error
- next step

A separate resilience test proves that a failed primary can degrade to a secondary node.

Real Supabase verification remains pending until a project is visible to the Supabase integration.

## Next convergence steps

1. Run AIrLab CI on this branch.
2. Fix any contract/test failures.
3. Open Memory Fabric V1 PR.
4. When a Supabase project becomes visible, convert the reference schema into a generated migration, apply it, run security/performance advisors and execute a real write/read/restart smoke test.
5. Build the AI-Orchestrator adapter over existing durable memory + CRDT instead of replacing them.
6. Add the future NAS provider behind the same provider contract.
