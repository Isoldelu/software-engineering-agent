# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Optional DeepSeek V4 Flash JSON Planner with non-thinking mode, local schema validation, deterministic fallback, and secret-safe Provider status.
- Explicit-budget 20-case real Provider A/B with required-Tool labels, latency/token/cost metrics, and retained Before/After reports.
- Step 34 multi-Worker Bridge fault experiment with database-level failure injection and real two-Worker HTTP concurrency.
- Idempotent concurrent release verification, orphan-Bridge compensation, rollout race checks, and retained audit evidence.
- Explicit retention protection for immutable Evolution/Policy Bridge records and Policy state.
- Reviewed Evolution-to-Policy Bridge for human-approved Router, Query Alias, and Retriever candidates.
- Immutable Candidate/Policy mapping records, SHA-256 provenance, idempotent rollout creation, and parameter-drift rejection.
- Runtime Policy support for query aliases and Hybrid Retriever configuration.
- FastAPI release/list endpoints, rollback state synchronization, Step 33 tests, evaluation, and documentation.

## [1.0.0] - 2026-08-24

### Added

- Multi-tool Software Engineering Agent for package, dependency, version, component, and document tasks.
- Hybrid planning, Evidence/Citation, deterministic verification, partial-success semantics, and replayable Trace.
- Hybrid RAG with BM25, RRF, reranking, stable Chunk IDs, and labeled retrieval evaluation.
- Controlled Feedback, offline failure mining, human-gated candidates, policy versioning, rollout, and rollback.
- Optional structured OpenAI Planner Provider with deterministic fallback and zero-cost offline default.
- FastAPI service, role-aware API Keys, PostgreSQL shared control plane, CAS, TTL leases, and schema migrations.
- Key rotation, Audit, retention, PostgreSQL pooling, Prometheus metrics, and checksum-protected backup/restore.
- 128 automated tests, 193 frozen evaluation cases, Docker build, and real PostgreSQL CI fault/load gates.

[1.0.0]: https://github.com/Isoldelu/software-engineering-agent/releases/tag/v1.0.0
