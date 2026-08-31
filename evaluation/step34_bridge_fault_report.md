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

The local HTTP run used a temporary SQLite shared control plane to exercise real Uvicorn process boundaries. GitHub Actions executes the same harness against PostgreSQL and uploads `software-agent-step34-bridge-evidence`; the remote Run and Artifact identifiers are appended after CI completion.

Paid Provider calls: `0`.
