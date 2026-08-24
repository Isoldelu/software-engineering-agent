# Step 28 Observability And Disaster Recovery

## Execution Decision

The preferred Step 28 action was to execute the PostgreSQL GitHub Actions job and retain its evidence. The current workspace has no `.git` directory, no GitHub remote, and no authenticated `gh` CLI, so a real Actions run cannot be triggered from this machine. The workflow remains executable and now uploads evidence as `software-agent-step28-postgres-evidence`.

## PostgreSQL Connection Pool

Each API Worker owns a `psycopg_pool.ConnectionPool`. Pools are never shared across processes.

```text
SOFTWARE_AGENT_DB_POOL_ENABLED=true
SOFTWARE_AGENT_DB_POOL_MIN_SIZE=1
SOFTWARE_AGENT_DB_POOL_MAX_SIZE=10
```

SQLite does not create a pool. `/storage/status` exposes only enabled/min/max/current/available/waiting values and never returns the connection URL or credentials. Worker shutdown closes its pool. A migration/startup failure also closes an already-created pool before failing startup.

The runtime dependency is `psycopg[binary,pool]`. PostgreSQL CI asserts that `pool.enabled=true`.

## Prometheus Metrics

`GET /metrics` requires at least a reader Key when authentication is enabled. Labels are restricted to method, route template, status, denial reason, and retention namespace. Query text, Session ID, Trace ID, Key fingerprint, package name, and request body are not labels.

Metrics include:

- `software_agent_http_requests_total`
- `software_agent_http_request_duration_seconds`
- `software_agent_auth_denials_total`
- `software_agent_audit_sink_failures_total`
- `software_agent_retention_deleted_total`
- `software_agent_storage_healthy`
- PostgreSQL pool size, available, and waiting gauges

The runtime uses official `prometheus-client` multiprocess files under `PROMETHEUS_MULTIPROC_DIR`, allowing one scrape to aggregate all Uvicorn Workers. A dependency-free fixed-bucket fallback keeps local tests usable when the optional runtime package is absent. The fallback stores only counters, sums, and ten fixed buckets, so memory use is constant.

## Independent Audit Outlet

Set `SOFTWARE_AGENT_AUDIT_LOG_PATH` to an append-only JSONL path, or `-` for stdout collection. Every event includes `schema_version=audit-event-v1`.

The independent sink runs in a `finally` path: if the database audit insert fails, file/stdout export is still attempted. Forbidden keys such as `api_key`, `secret`, `secret_hash`, `request_body`, and `query` reject the exported event. Sink failures increment a Prometheus counter and never break the user request.

The JSONL output should be collected by the deployment log agent and written to a separate immutable audit store. A local file is an outlet, not a complete SIEM or tamper-proof archive.

## Logical Backup And Restore

Create a backup:

```bash
python -B -m app.storage.backup_cli --create backups/control-plane.json
```

Limit it to selected namespaces:

```bash
python -B -m app.storage.backup_cli --create backups/traces.json --namespace trace --namespace session
```

Verify and restore:

```bash
python -B -m app.storage.backup_cli --verify backups/control-plane.json
python -B -m app.storage.backup_cli --restore backups/control-plane.json --clear-existing
```

The manifest contains format version, timestamp, record count, and SHA-256. Restore verifies integrity before taking the `control-plane-restore` lease. The logical backup contains `control_plane_records` only. API Key Registry and Audit are excluded; production database-level encrypted backups remain necessary for complete disaster recovery.

CI runs `evaluation/backup_restore_drill.py`: create two records, snapshot, verify, delete, restore, compare, and clean up.

## Retained CI Evidence

The PostgreSQL job writes and uploads:

- `postgres-smoke.json`
- `fault-injection.json`
- `backup-restore.json`
- `load-before-worker-fault.json`
- `load-after-worker-fault.json`
- `storage-status.json`
- `prometheus-metrics.txt`
- `database-outage.txt`
- `audit.jsonl`

Artifact upload uses `if: always()` so partial evidence remains available after a failed gate.

## Remaining Boundary

- GitHub Actions has not run because this folder is not a Git repository and has no GitHub credentials.
- PostgreSQL pool behavior, multiprocess Prometheus aggregation, and database outage recovery are implemented CI gates, not local measurements.
- Local backup/restore and audit tests use SQLite WAL.
- Production still needs encrypted physical backups, restore-point objectives, off-host retention, alert rules, dashboard provisioning, and a managed audit destination.
