# Step 27 Production Operations

## Purpose

Step 27 turns the Step 26 shared control plane into an operable deployment boundary. It adds checksum-protected schema migrations, database-managed API Key rotation, redacted audit events, bounded retention, concurrent load measurement, and isolated worker/database fault injection.

## Schema Migration

Startup applies migrations under one transaction. PostgreSQL also takes a transaction-level advisory lock so only one Worker migrates at a time.

| Version | Change |
|---:|---|
| 1 | Record Store and TTL Lease tables |
| 2 | API Key Registry and Audit table |
| 3 | Retention and role/status lookup indexes |

`control_plane_schema_migrations` stores version, name, checksum, and application time. A mismatch between an applied checksum and source migration raises `MigrationChecksumError` and fails startup. Existing Step 26 databases are adopted through idempotent `CREATE IF NOT EXISTS` statements.

`GET /storage/status` reports the current and latest version without exposing database credentials.

## Key Rotation

Environment Keys bootstrap the service. An administrator can then rotate a role into the shared Registry:

```http
POST /auth/keys/rotate
X-API-Key: <admin-key>

{"role":"operator","grace_seconds":300,"ttl_seconds":2592000}
```

The new secret is returned once. Only `SHA-256(pepper:key)` is stored. Configure `SOFTWARE_AGENT_API_KEY_PEPPER` through the deployment secret manager. Once a role has any Registry history, that role no longer accepts its environment Key. All Workers query the Registry per request, so rotation and revocation are immediately shared.

The final usable database-managed admin Key cannot be revoked. Rotate it first, verify the new Key, then revoke the old Key after the grace window.

## Audit

`control_plane_audit` records authentication/authorization denials, protected API outcomes, Key changes, and retention runs. Events contain a 12-character Key fingerprint, role, path, method, status, and timestamp. Raw Keys, secret hashes, request bodies, queries, and Agent context are excluded.

Administrators can query a bounded window with `GET /audit/events?limit=100&since=<unix-time>`.

## Trace Retention

Default periods are Session 7 days, Trace 30, Feedback/Candidates 90, evolution transient data 30, and Audit 180. Override a period with `SOFTWARE_AGENT_RETENTION_<NAMESPACE>_DAYS`.

Preview first:

```bash
python -B -m app.maintenance.retention_job --batch-limit 1000
```

Apply one bounded batch:

```bash
python -B -m app.maintenance.retention_job --apply --batch-limit 1000
```

The equivalent admin endpoint is `POST /maintenance/retention/run`. Production scheduling remains an external responsibility such as cron, Kubernetes CronJob, or a managed scheduler. Policy state is deliberately excluded from time-based deletion.

## Load And Fault Gates

```bash
python -B evaluation/postgres_smoke.py
python -B evaluation/step27_fault_eval.py
python -B evaluation/step27_load.py --api-key <operator-key> --requests 100 --concurrency 16
```

The load report includes success rate, 5xx count, p50/p95 latency, and observed Worker PIDs. The fault suite verifies stale CAS rejection, lease contention, expired lease recovery, transaction rollback, migration version, and health.

The CI PostgreSQL job additionally:

1. Starts PostgreSQL 16 and two Uvicorn Workers.
2. Runs 100 concurrent Agent requests and requires both Workers to be observed.
3. Kills one Worker, waits for supervisor replacement, and reruns load.
4. Stops PostgreSQL, requires `/ready` to return 503, restarts it, and requires readiness recovery.

## Honest Boundary

Local acceptance used SQLite WAL because the workstation Docker image remains unavailable due disk capacity. Real PostgreSQL, Worker kill, and database outage scenarios are configured as executable GitHub Actions gates; they must not be described as locally executed until that job has run successfully. Connection pooling, backups, Secret Manager integration, metrics export, and a production retention scheduler remain deployment work.
