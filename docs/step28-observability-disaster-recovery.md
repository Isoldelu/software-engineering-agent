# Step 28 Observability And Disaster Recovery

## Execution Decision

The workspace initially had no Git repository or GitHub remote. It was initialized, committed with a GitHub noreply author, uploaded to the private `Isoldelu/software-engineering-agent` repository, and authenticated through Git Credential Manager.

GitHub Actions Run `32738626804` completed successfully on commit `53405f1`. All three jobs passed: test-and-evaluate, docker-build, and postgres-integration. Artifact `software-agent-step28-postgres-evidence` has ID `9524236638` and expires on 2026-11-22.

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

Real PostgreSQL results from Run `32738626804`:

| Gate | Result |
|---|---:|
| PostgreSQL schema | control-plane-v3, up to date |
| Shared record and exclusive lease | Passed |
| Transaction/lease fault gates | 6/6 passed |
| Initial load | 100/100, 0 server errors |
| Initial latency | p50 145.74 ms, p95 456.14 ms |
| Initial Workers | PID 2583 and 2584 |
| Recovery load after Worker kill | 40/40, 0 server errors |
| Recovery latency | p50 85.99 ms, p95 279.13 ms |
| Replacement Worker | PID 2667 replaced PID 2583 |
| PostgreSQL Pool | enabled, max 8, waiting 0 |
| Backup/restore | 2 deleted and 2 restored |
| Database outage | ready 503, recovered 200 |
| Audit | 142/142 schema-valid lines, no Key/Query leak |
| Prometheus | request and pool metrics present, no Query leak |

## Remaining Boundary

- The local workstation still does not run PostgreSQL or Docker; real PostgreSQL evidence comes from the linked GitHub-hosted runner.
- CI latency is a short functional load gate, not a capacity limit or production SLA.
- Production still needs encrypted physical backups, restore-point objectives, off-host retention, alert rules, dashboard provisioning, and a managed audit destination.
