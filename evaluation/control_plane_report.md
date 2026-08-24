# Step 26 Control-plane Evaluation Report

## Result

```text
Local backend under test: SQLite WAL
Deployment backend: PostgreSQL 16
Independent Store instances: 2
Control-plane gates: 13/13 passed
Concurrent Policy versions: [2, 3]
Paid API calls: 0
```

## Passed Gates

- Shared JSON records are visible across independent connections.
- Stale revisions are rejected by compare-and-swap.
- Database leases are exclusive and recoverable.
- Session Context is visible across workers.
- Trace and Feedback are visible across workers.
- A stale Evolution Candidate review cannot overwrite the winning review.
- Concurrent Policy creation produces unique v2/v3 versions.
- Policy state is consistent across independent repositories.
- Admin inherits reader permissions; reader cannot execute operator actions.
- Authentication status does not expose API Key values.
- Database readiness succeeds.

## HTTP Integration

The final local integration started one Uvicorn parent and two server workers against the same SQLite WAL control plane.

```text
No API Key -> GET /tools: 401
reader -> GET /tools: 200
reader -> POST /agent/query: 403
operator -> POST /agent/query: 200
operator -> POST policy rollback: 403
admin -> policy handler reached: 409 for missing policy
Cross-request Trace read: 200
Shared multi-turn Session: turn_count=2, package=openssl
Readiness: ready
Credentials exposed: false
```

## Scope Boundary

The current machine did not run a PostgreSQL container because local Docker installation was previously deferred for insufficient disk space. PostgreSQL support is implemented through `psycopg`, Compose is configured for two API workers, and CI contains a real PostgreSQL service smoke job. Until that job or another PostgreSQL environment is actually executed, describe the result as “PostgreSQL-ready shared persistence with local SQLite WAL concurrency validation,” not “locally deployed PostgreSQL.”
