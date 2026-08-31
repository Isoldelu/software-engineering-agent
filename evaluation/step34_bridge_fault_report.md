# Step 34 Bridge Fault Report

## Local Database Fault Injection

| Metric | Result |
|---|---:|
| Concurrent release requests | 20/20 success |
| Policy versions created for one Candidate | 1 |
| Immutable Bridge records | 1 |
| Creator / idempotent replay | 1 / 19 |
| Competing Candidate behavior | 1 winner / 1 explicit conflict |
| Temporary orphan after injected write failure | 1 |
| Final orphan after retry | 0 |
| Promote/rollback final stable Policy | `deterministic-policy-v1` |
| Gates | 16/16 passed |

The fault suite exposed an initial observability race where the Policy creator and Bridge creator could be different requests, leaving zero responses marked as the complete creator even though persisted cardinality was correct. A Candidate-scoped cross-Worker lease now covers the normal Policy-to-Bridge release section. Five consecutive reruns passed the unique-creator gate.

## Local Two-Worker HTTP Experiment

| Metric | Result |
|---|---:|
| Observed Worker PIDs | 2 |
| Concurrent HTTP release requests | 20/20 success |
| Server errors | 0 |
| Policy IDs | 1 |
| Creator / idempotent replay | 1 / 19 |
| Release audit events | 20 |
| Raw API Key in results | 0 |
| Rollback | passed |
| Gates | 14/14 passed |

The local HTTP run used a temporary SQLite shared control plane to exercise real Uvicorn process boundaries.

## Real PostgreSQL CI Evidence

- Commit: `436b83568cc6984f910642136d9af86bbe98c918`.
- GitHub Actions Run: `33363220127`, conclusion `success`.
- `test-and-evaluate` Job `99398550631`: success.
- `docker-build` Job `99398550692`: success.
- `postgres-integration` Job `99398550716`: success.
- PostgreSQL step `Step 34 PostgreSQL Bridge fault injection`: success.
- PostgreSQL step `Step 34 two-worker concurrent Bridge release`: success.
- Artifact `software-agent-step34-bridge-evidence`: ID `9747392859`, 1797 bytes, `expired=false`, expires 2026-11-29.

Paid Provider calls: `0`.
