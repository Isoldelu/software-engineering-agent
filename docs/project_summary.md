# Project Summary

## Project Name

AI Software Engineering Agent

## Positioning

This project is a compliant AI4SE demo based only on public or simulated data. It reproduces the methodology of a software engineering Agent without using or copying any internal enterprise data.

The system focuses on software asset query and analysis tasks:

- Package metadata lookup
- Dependency analysis
- Version comparison
- Component ownership mapping
- RAG retrieval over release notes and manuals
- Hybrid multi-tool planning
- Agent trajectory logging
- Stable structured Evidence and Citation for Tool facts
- Deterministic online verification and partial-success execution semantics
- Hybrid RAG with BM25, RRF, deterministic reranking, and stable Chunk IDs
- Session-scoped multi-turn Context and privacy-bounded replayable Trace
- Controlled Trace-linked Feedback and human-reviewed configuration candidates
- Versioned policy release, deterministic gray rollout, monitoring, and rollback
- Optional real LLM planning provider with offline/online dual-mode evaluation
- Offline failure mining, root-cause clustering, and human-gated shadow candidates
- Reviewed Evolution-to-Policy translation, immutable provenance, idempotent rollout, and rollback
- Shared PostgreSQL-ready control-plane persistence and role-aware API authentication
- Benchmark evaluation and bad-case optimization

## Architecture

```mermaid
flowchart TD
    Q["User Query"] --> P["Agent Router / Planner"]
    P --> T["Tool Calling Layer"]
    T --> PKG["PackageSearchTool"]
    T --> DEP["DependencyAnalysisTool"]
    T --> VER["VersionCompareTool"]
    T --> CMP["ComponentMappingTool"]
    T --> RAG["RAGRetrieverTool"]
    PKG --> KB["Simulated Software Knowledge Base"]
    DEP --> KB
    VER --> KB
    CMP --> KB
    RAG --> DOC["Release Notes / Manuals"]
    KB --> A["Structured Answer"]
    DOC --> A
    A --> TRAJ["Trajectory Logging"]
    TRAJ --> EVAL["Benchmark / Bad Case / Robustness Evaluation"]
```

## Core Design

The Agent follows this workflow:

```text
Query -> Intent Routing -> Tool Selection -> Tool Execution -> Evidence -> Answer -> Evaluation
```

The project keeps deterministic local tools so evaluation is reproducible, while also exposing prompt and function schema layers for future LLM Router or Function Calling integration.

## Evaluation Layers

The project has four evaluation layers:

```text
Software-Agent-Bench: standard tool-calling benchmark
Software-Agent-Challenge: bad-case optimization suite
Software-Agent-Robustness: ambiguous engineering-query suite
Software-Agent-Large-Bench: 170-case experiment benchmark
```

Step 20 adds a separate 30-case labeled RAG benchmark comparing Legacy, BM25, and Hybrid retrieval. Hybrid reaches 100% Recall@3/5, 95.83% MRR, 100% no-answer accuracy, and 100% Citation correctness on the simulated corpus.

Step 21 adds 8 multi-turn conversations and 5 isolation probes. Entity consistency, Trace completeness, and replay input reconstruction are 100%, with zero cross-session leaks.

Step 22 adds a controlled optimization experiment. Three Trace-linked `wrong_tool` records generate a Router Hook candidate that improves linked routing from 0% to 100%, fixes 3 bad cases, and keeps all 193 frozen regression cases unchanged. The candidate stops at `pending_review` and cannot be activated before Step 23.

Step 23 adds controlled delivery. An approved candidate becomes an immutable policy version, 20% of sessions are selected by stable SHA-256 assignment, each Trace records its exact policy, and control/rollout metrics can automatically restore the parent policy. The evaluation observed an 18.4% rollout cohort over 1,000 sessions and completed rollback without changing Agent source hashes.

Engineering delivery is split into runtime/development dependencies, Docker and Compose, GitHub Actions gates, a CI smoke benchmark, and release/rollback runbooks.

Step 24 keeps the deterministic planner as the zero-cost default and adds an optional OpenAI Responses structured-plan adapter. Provider outputs are locally validated before execution; missing credentials, timeout, malformed JSON, API errors, and unknown tools safely fall back or fail closed. A 12-case Mock Online evaluation reaches 100% plan parity and fallback success with zero paid calls.

Step 25 adds offline controlled self-evolution without requiring a Provider. The miner discovers 9 reproducible failures and clusters Router, Query Alias, and Retriever ranking causes into 3 configuration candidates. Shadow evaluation fixes all 9 linked cases with zero regressions across the corresponding 193-case Agent and 30-case RAG suites. Every candidate stops at `pending_review`; source editing and automatic activation remain blocked.

Step 26 adds a shared control plane for Session, Trace, Feedback, Evolution, and Policy records. Revision-based compare-and-swap prevents stale writes; database leases serialize Policy mutation and Evolution scans. API Key roles separate read, execution, and approval/release permissions. Local SQLite WAL tests use two independent Store instances and pass all 13 consistency gates, while PostgreSQL 16, two Uvicorn workers, readiness, and a real-database CI smoke are configured for deployment.

Step 27 adds production operations around that control plane. Three versioned migrations are protected by checksums and a PostgreSQL advisory lock. API Keys can be rotated or revoked through a shared hashed Registry, protected actions create redacted Audit events, and configurable bounded retention covers Session, Trace, Feedback, Evolution, and Audit data. Local two-Worker load passed 60/60 requests; after killing one Worker, its replacement passed 40/40 recovery requests. Real PostgreSQL load, Worker recovery, and database stop/readiness/restart gates are implemented in CI and remain pending execution outside this disk-constrained workstation.

Step 28 adds per-Worker PostgreSQL connection pools, official Prometheus multiprocess metrics with a constant-memory local fallback, an independent redacted JSONL Audit outlet, and checksum-protected logical backup/restore. The local recovery drill restored 2/2 records and rejected a corrupted snapshot. GitHub Actions Run `32742656550` passed 128 tests plus Docker and PostgreSQL jobs: 100/100 initial and 40/40 post-Worker-kill requests succeeded with zero server errors; Pool, Audit, Metrics, backup/restore, and database stop/recovery gates passed. The evidence is retained in the v1.0.0 Release and Actions artifact.

Step 29 packages the project as a reproducible v1.0.0 release with open-source governance,
public-risk audit, release notes, machine-readable evidence, and a fixed evidence asset. A real
release-candidate latency-gate failure was diagnosed and fixed with median statistics plus a bounded
noise floor instead of being hidden by a retry.

Step 30 provides an interview delivery layer: a one-page architecture and evidence showcase, a
2-3 minute demo runbook, an executable API demo client, current interview Q&A, and browser-verified
screenshots. GitHub Actions Run `33314875879` passed 138 tests plus Docker and PostgreSQL jobs.
This layer changes presentation, not the frozen Agent behavior.

Step 33 closes the previously explicit Evolution/Policy gap. A human-approved, Shadow-passed
Router, Query Alias, or Retriever candidate is translated into the shared Policy schema, merged
with the stable configuration, bound to Candidate/Config SHA-256 digests, and released through an
immutable idempotent Bridge record. Runtime Policy assignment now applies all three asset types;
manual or monitored rollback restores the parent version and synchronizes the source candidate.
The Agent still cannot approve or activate itself. GitHub Actions Run `33354020784` passed the
150-test suite plus Docker and real PostgreSQL integration jobs.

Latest summary:

```text
suite_count: 4
total_cases: 193
total_bad_cases: 0
all_suites_passed: true
```

## Baseline Experiment

Offline proxy baselines are used to avoid paid LLM API cost and nondeterministic outputs:

```text
DirectLLMProxy task_success: 22.94%
RAGOnlyProxy task_success: 57.06%
Agent task_success: 100.00%
```

Optimization experiment:

```text
Legacy keyword router tool_accuracy: 61.76%
Optimized Agent tool_accuracy: 100.00%
Absolute improvement: +38.24%
```
