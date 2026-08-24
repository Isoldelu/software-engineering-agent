# Step 27 Operations Evaluation Report

## Scope

This report separates locally executed evidence from PostgreSQL CI gates that are implemented but not yet executed on this disk-constrained workstation.

## Locally Executed Results

| Gate | Result |
|---|---:|
| Migration apply/idempotence/checksum tests | Passed |
| Step 26 legacy schema adoption | Passed without data loss |
| Key rotation, grace, revocation, cross-Store authentication | Passed |
| Audit redaction and retention dry-run/apply | Passed |
| Transaction fault gates | 6/6 passed |
| First multi-Worker load | 60/60, 0 server errors |
| First observed Workers | PID 20404 and 22160 |
| First latency | p50 358.22 ms, p95 1374.40 ms |
| Worker kill | PID 20404 terminated |
| Replacement Worker | PID 23292 observed |
| Recovery load | 40/40, 0 server errors |
| Recovery latency | p50 218.07 ms, p95 847.12 ms |
| HTTP Key rotation | old Key 401, new Key 200 |
| Registry secret exposure | false |
| Full automated tests | 119 passed |
| Frozen compatibility baseline | 193 cases compatible |

The local load used two Uvicorn Workers with a shared temporary SQLite WAL database. The transaction suite injected stale CAS, active lease contention, lease expiry, and an exception inside a write transaction; all recovery assertions passed.

## PostgreSQL CI Gates

The `postgres-integration` workflow now uses PostgreSQL 16 and executes:

- Migration-aware PostgreSQL smoke.
- Six deterministic transaction/lease fault gates.
- 100 requests at concurrency 16 across two Workers.
- Forced termination and replacement of one Worker, followed by 40 recovery requests.
- PostgreSQL container stop/start with `/ready` expected to transition 503 to 200.

Status: implemented, pending execution in GitHub Actions or another real PostgreSQL environment. These figures must not be reported as completed PostgreSQL measurements before CI evidence exists.
