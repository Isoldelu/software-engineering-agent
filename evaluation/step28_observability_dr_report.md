# Step 28 Observability And DR Report

## Locally Executed

| Gate | Result |
|---|---:|
| Step 26-28 focused tests | 24 passed |
| SQLite pool disabled/redacted status | Passed |
| Fixed-bucket Prometheus fallback | Passed |
| Route-template label and secret exclusion | Passed |
| Independent JSONL Audit export | Passed |
| Audit export after injected DB failure | Passed |
| Forbidden audit field rejection | Passed |
| Logical backup checksum verification | Passed |
| Corrupted backup rejection | Passed |
| Backup/delete/restore comparison | 2/2 records restored |
| API Key Registry included in backup | false |
| Audit included in backup | false |
| New module Ruff | Passed |
| Step 28 Mypy | 20 modules passed |

## GitHub Actions Status

Executed successfully.

- Repository: `Isoldelu/software-engineering-agent` (private)
- Commit: `53405f1f65cdb5963f2515bde3c477e94a202539`
- Run: `32738626804`
- Artifact: `software-agent-step28-postgres-evidence`, ID `9524236638`
- Artifact expiry: 2026-11-22
- test-and-evaluate: success
- docker-build: success
- postgres-integration: success

## Real PostgreSQL Results

| Gate | Result |
|---|---:|
| Shared record | Passed |
| Lease exclusive | Passed |
| Schema | control-plane-v3, current=latest=3 |
| Fault injection | 6/6 passed |
| Initial load | 100/100 success, 0 server errors |
| Initial workers | 2583, 2584 |
| Initial latency | p50 145.74 ms, p95 456.14 ms |
| Post-kill recovery load | 40/40 success, 0 server errors |
| Replacement worker | 2667 |
| Recovery latency | p50 85.99 ms, p95 279.13 ms |
| Pool | enabled, min 1, max 8, waiting 0 |
| Backup/restore | checksum passed, 2/2 restored |
| PostgreSQL outage | `/ready` 503 while down, 200 after restart |
| Audit JSONL | 142 lines, all schema-valid, no raw Key/Query |
| Prometheus | request and pool metrics present, no Query label |

## Interpretation

Step 28 now has both local deterministic evidence and a real PostgreSQL CI run. The measured latency is evidence for this 100-request functional gate, not a production capacity claim.
