# Control-plane Persistence, Authentication, and Consistency

## 1. Purpose

Step 26 replaces process-local control-plane state with an optional shared database and adds role-aware API authentication. The default remains memory/file mode so the frozen offline demo stays backward compatible.

When `SOFTWARE_AGENT_DATABASE_URL` is configured, these records are shared by all workers:

- Session Context
- Trace
- Feedback
- Step 22 Policy Candidate
- Step 25 Failure, Cluster, and Evolution Candidate
- Policy version, stable/rollout assignment, and rollback state

## 2. Storage Backends

| Environment | Backend | Purpose |
|---|---|---|
| Local tests | SQLite WAL | Reproducible multi-connection consistency tests without Docker |
| Deployment | PostgreSQL 16 | Shared state for multiple API processes or containers |
| No database URL | Memory + existing policy JSON | Step 17 compatibility mode |

PostgreSQL support uses a lazy `psycopg` import. Credentials are read only from `SOFTWARE_AGENT_DATABASE_URL` and are never returned by `/storage/status`.

## 3. Consistency Model

The shared schema contains JSON records and leases. Step 27 manages it through three checksum-protected migrations:

```text
control_plane_records(namespace, record_id, payload, version, updated_at)
control_plane_leases(name, owner, expires_at)
```

- Every mutable record has an integer revision.
- Repository updates use compare-and-swap with `expected_version`.
- A stale Feedback/Evolution/Session write returns a conflict instead of overwriting newer state.
- Policy writes additionally acquire the `policy-state-write` database lease.
- Policy requests wait at most 3 seconds, then fail with HTTP 409.
- Evolution scan uses a 120-second fail-fast lease so two workers cannot clear and rebuild the cycle simultaneously.
- Lease TTL allows another worker to recover after a process terminates.

## 4. API Authentication

Authentication is disabled by default for local compatibility. Enable it with:

```text
SOFTWARE_AGENT_AUTH_ENABLED=true
SOFTWARE_AGENT_READER_API_KEY=...
SOFTWARE_AGENT_OPERATOR_API_KEY=...
SOFTWARE_AGENT_ADMIN_API_KEY=...
```

The request header is `X-API-Key`.

| Role | Permission |
|---|---|
| reader | GET data, tools, traces, status, and evaluation reports |
| operator | reader permissions plus Agent execution, feedback, scan, replay, and shadow evaluation |
| admin | operator permissions plus review, policy mutation, activation attempts, and session deletion |

Higher roles inherit lower-role permissions. Missing or invalid keys return 401, insufficient roles return 403, and enabled authentication without configured keys fails closed with 503. Key values never enter responses, Trace, or logs; only a short SHA-256 fingerprint is attached to the in-request principal.

Public endpoints are limited to `/health`, `/ready`, `/auth/status`, `/demo`, and API documentation.

## 5. Deployment

`docker-compose.yml` defines PostgreSQL 16 and starts Uvicorn with two workers. Set non-placeholder database and API credentials before deployment.

```bash
docker compose up --build
```

Readiness uses `/ready`, which checks the configured database. `/health` remains a process liveness check.

The GitHub Actions `postgres-integration` job starts a real PostgreSQL service and runs `evaluation/postgres_smoke.py`. Local Docker/PostgreSQL execution remains deferred on the current machine because of disk capacity; the SQLite WAL evaluation validates the same SQL record, revision, and lease semantics locally.

Step 27 extends that job with concurrent two-Worker load, Worker termination/recovery, transaction fault injection, and a PostgreSQL stop/readiness/restart scenario. See `docs/step27-production-operations.md`.

## 6. Commands

```bash
python -B evaluation/eval_runner.py --suite control-plane
python -B -m pytest -q tests/test_control_plane.py -p no:cacheprovider
```

API endpoints:

```text
GET /auth/status
GET /storage/status
GET /ready
GET /evaluation/control-plane
```

## 7. Step 27 Operations

- Versioned schema history with checksum drift rejection and PostgreSQL advisory locking.
- Database-managed Key rotation, grace windows, revocation, and shared Worker visibility.
- Structured redacted Audit events.
- Configurable, bounded Session/Trace/Feedback/Evolution/Audit retention.
- Multi-Worker load and isolated Worker/PostgreSQL fault gates in CI.

## 8. Remaining Production Work

- Add connection pooling and database-level performance dashboards.
- Put the Key pepper and bootstrap secrets in a managed Secret Manager.
- Schedule the implemented retention CLI/API and define backup/restore objectives.
- Execute and retain the PostgreSQL CI artifacts before making production performance claims.
