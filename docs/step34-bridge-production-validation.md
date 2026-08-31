# Step 34: Multi-Worker Bridge Production Validation

## Purpose

Step 33 proved that an approved Evolution Candidate can become a governed Policy. Step 34 tests the failure boundary around that release path: concurrent Workers, duplicate requests, competing candidates, a partial write, and promote/rollback contention.

The goal is not to claim distributed-transaction perfection. It is to show bounded, observable recovery for the current shared-database design.

## Fault Model

| Scenario | Expected invariant |
|---|---|
| Same Candidate released by many Workers | One Policy, one immutable Bridge, remaining requests are idempotent replays |
| Different Candidates compete for one rollout | One winner and one explicit conflict; no silent overwrite |
| Failure after Policy creation, before Bridge persistence | Temporary orphan is observable; retry reuses the Policy and repairs the Bridge |
| Promote and rollback contend | State remains bounded and rollback restores the parent Policy |
| Retention job runs | Policy state and Candidate-to-Policy attribution are never pruned by generic TTL rules |
| Audited HTTP release | Actor role and action are retained; raw API Key is absent |

## Evaluation Layers

Database-level fault injection:

```bash
python -B evaluation/step34_bridge_fault_eval.py
```

This uses two independent Store/Repository instances. It can run against a temporary SQLite database locally or the PostgreSQL database supplied by `SOFTWARE_AGENT_DATABASE_URL` in CI.

Real multi-Worker HTTP experiment:

```bash
python -B evaluation/step34_bridge_http.py --prepare
uvicorn app.api.server:app --host 127.0.0.1 --port 8010 --workers 2
python -B evaluation/step34_bridge_http.py --base-url http://127.0.0.1:8010 --api-key <admin-key> --requests 20 --concurrency 8
```

The HTTP harness requires authentication and records observed `X-Agent-Worker-Pid` values to prove that at least two Workers handled release requests.

## Compensation Semantics

Policy creation and immutable Bridge persistence cannot be expressed as one repository call because they belong to separate state models. The release service therefore uses a Candidate-scoped cross-Worker lease, a deterministic source identifier, and idempotent `create_rollout_once()` behavior:

1. Acquire the Candidate-scoped release lease shared by all Workers.
2. Create or recover the Policy using the Candidate source identifier.
3. Persist the immutable Bridge mapping.
4. If step 3 fails, the Policy may be temporarily visible without a Bridge and the lease is released.
5. A retry reacquires the lease, finds the existing Policy, verifies rollout parameters and Candidate/config digests, then writes the missing Bridge.
6. Parameter drift is rejected instead of silently changing the existing release.

This is retry compensation with an observable temporary orphan, not an unqualified atomic transaction claim.

## Retention Boundary

`evolution_policy_bridge` and `policy_state` are protected namespaces. Generic retention may prune bounded operational records such as old Trace or Audit data, but it must not destroy release attribution or Policy history. A future archival workflow may move these records only if it preserves digests and referential integrity.

## Local Acceptance Results

- Database experiment: 20/20 concurrent requests, one Policy, one Bridge, 16/16 gates.
- Injected partial write: one temporary orphan, zero final orphans after retry.
- Real HTTP experiment: two Worker PIDs, 20/20 success, zero server errors.
- HTTP idempotency: one creator and 19 replays, one Policy ID.
- Audit: 20 release events with admin attribution and no raw Key.
- Rollback: source Candidate inactive, no active rollout, parent Policy restored.
- HTTP gates: 14/14.
- Paid Provider calls: 0.

## Honest Boundaries

- Local results do not establish production throughput, availability SLA, or exactly-once delivery under every network partition.
- The temporary Policy-without-Bridge window is tolerated and repaired by retry; it is deliberately reported rather than hidden.
- Candidate approval and release remain explicit human/admin actions. The Agent cannot approve itself or bypass the Bridge.
- Real Provider A/B remains independent and requires an explicit API Key and budget.
