# Software Engineering Agent v1.0.0

The first reproducible release of the simulated-data AI4SE Agent.

## Highlights

- Five specialized tools with deterministic and hybrid multi-tool planning.
- Hybrid RAG, structured Evidence/Citation, Verifier, and partial-success semantics.
- Replayable Trace, controlled Feedback, offline candidate generation, human review, gray rollout, and rollback.
- FastAPI, PostgreSQL shared state, role-aware Key management, migrations, Audit, retention, pooling, metrics, and backup/restore.

## Verified Results

- 128 automated tests passed.
- 193 frozen evaluation cases remained compatible.
- Real PostgreSQL CI completed 100/100 initial requests and 40/40 recovery requests with zero server errors.
- Six transaction/lease fault gates passed.
- Worker replacement and PostgreSQL readiness 503-to-200 recovery passed.
- Backup verification and 2/2 record restore passed.
- Prometheus and 142-line Audit evidence contained no raw query or API Key.

Evidence is bound to commit `01a47379d3d3cd975fababf3c133beae99702eec` and GitHub Actions Run `32742656550`.

## Boundaries

- All software-asset data is simulated.
- Offline proxy baselines are not real LLM performance measurements.
- CI latency is a functional load result, not a production SLA.
- Online Provider A/B remains optional and requires an explicit API budget.
