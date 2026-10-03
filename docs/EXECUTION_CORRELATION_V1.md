# Execution Correlation V1

Status: P0 contract for M1-03 Durable Orchestrator.

## Ownership

Cantiere remains authoritative for:

- Project;
- Task;
- Execution;
- Attempt;
- checkpoint/resume;
- Reviewer/validation;
- owner approval/apply.

AIrLab does **not** create a second lifecycle. It carries a bounded correlation identity as subordinate evidence for remote/provider work.

## ExecutionCorrelation payload

Version 1 uses these fields:

```json
{
  "schema_version": 1,
  "project_id": "project-abc",
  "task_id": "task-42",
  "execution_id": "execution-123",
  "attempt_id": "attempt-1",
  "operation_id": "software.build",
  "request_fingerprint": "<lowercase sha256 hex>",
  "idempotency_key": "airlab:v1:<sha256 hex>",
  "checkpoint_id": "checkpoint-1"
}
```

`checkpoint_id` is optional. Every other field is required.

`request_fingerprint` identifies only the bounded, non-secret semantic request identity needed to distinguish changed external work. It must never be built from provider credentials, user secrets, or arbitrary private payloads merely to obtain a hash.

## Idempotency semantics

The same logical external operation MUST keep the same `idempotency_key` across:

- a newer Cantiere `attempt_id`;
- a newer checkpoint;
- retry after a retryable failure;
- provider failover;
- a changed provider-side remote job id.

The key MUST change when any of these change:

- `project_id`;
- `task_id`;
- `execution_id`;
- `operation_id`;
- `request_fingerprint`.

`attempt_id`, `checkpoint_id`, provider id and remote job id are deliberately excluded from key derivation.

A new Cantiere attempt therefore does not authorize a duplicate external operation. It first reuses/watches/retries the same idempotent operation unless Cantiere creates a genuinely new logical execution/request identity.

## Key derivation algorithm

1. Build this object with normalized non-empty UTF-8 strings:

```json
{
  "execution_id": "...",
  "operation_id": "...",
  "project_id": "...",
  "request_fingerprint": "...",
  "task_id": "..."
}
```

2. Encode as UTF-8 JSON with:
   - keys sorted lexicographically;
   - no insignificant whitespace;
   - Unicode preserved rather than ASCII-escaped.
3. Calculate SHA-256 over those bytes.
4. Prefix the lowercase digest with `airlab:v1:`.

Python reference settings are equivalent to:

```text
json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

## Cross-language test vector

Input:

```text
project_id          = project-abc
task_id             = task-42
execution_id        = execution-123
operation_id        = software.build
request_fingerprint = db5c57fcf1b8861cc7469c311cf073c96d0d377fa2291ac09656f450f2304b2c
```

Canonical JSON:

```json
{"execution_id":"execution-123","operation_id":"software.build","project_id":"project-abc","request_fingerprint":"db5c57fcf1b8861cc7469c311cf073c96d0d377fa2291ac09656f450f2304b2c","task_id":"task-42"}
```

Expected key:

```text
airlab:v1:1637d6cf216f94593ac4e97bbb1bce0841553d46922a2ec754df8a8fe7eca701
```

The Dart mirror must pass this exact vector before the contract is used across HTTP/provider boundaries.

## Remote execution evidence vocabulary

AIrLab/provider evidence uses only these subordinate states:

- `accepted`
- `running`
- `succeeded`
- `retryable_failure`
- `terminal_failure`
- `cancelled`

They map to bounded recovery actions:

| Remote state | Cantiere-facing action | Meaning |
| --- | --- | --- |
| `accepted` | `watch` | Operation is already accepted; do not submit a duplicate. |
| `running` | `watch` | Operation is still running; do not submit a duplicate. |
| `succeeded` | `reuse_result` | Reuse verified result/evidence; do not replay. |
| `retryable_failure` | `retry_same_key` | Retry/fail over with the same idempotency key. |
| `terminal_failure` | `stop` | Fail closed; Cantiere decides any new logical execution. |
| `cancelled` | `stop` | Never auto-replay cancelled external work. |

These states are evidence, not replacements for Cantiere execution states.

## Provider failover

Provider identity and provider remote-job identity are evidence only. They are not included in `idempotency_key`.

If provider A returns a retryable failure and policy selects provider B, provider B receives the same external-operation idempotency key. The Cantiere Execution remains the same logical execution, while the current Cantiere Attempt remains independently observable.

## Security and diagnostics

Correlation/evidence payloads may contain technical IDs, status, provider id, remote job id and bounded detail codes.

They must not contain by default:

- prompts;
- generated file contents;
- conversation text;
- API keys/secrets;
- arbitrary user data.

## V1 exclusions

This contract does not yet:

- alter `/v1/tasks`;
- persist remote jobs;
- schedule retries;
- choose providers;
- approve or apply repository changes;
- define monetary `ResourceBudget` policy.

Those are later integration steps built on this identity contract.
