# Offline Controlled Self-Evolution

## 1. Purpose

Step 25 moves the project from a feedback-only candidate loop to offline proactive discovery. The Agent can now scan labeled evaluation results, identify repeated failure patterns, propose bounded configuration changes, and test them in shadow mode without an API key.

This is controlled self-evolution, not autonomous self-modification. The system cannot edit Python source, datasets, test assertions, permissions, or release gates, and no candidate can activate itself.

## 2. Flow

```text
Offline Benchmark / Trace Result
  -> Failure Mining
  -> Root-cause Clustering (minimum support: 2)
  -> Configuration Candidate
  -> Linked Shadow Evaluation
  -> Frozen Regression Evaluation
  -> pending_review
  -> Human approve/reject
  -> Separate reviewed release path
```

## 3. Candidate Types

| Failure type | Candidate asset | Isolated action |
|---|---|---|
| `router_miss` | `router_rule` | Supplies a matching validated Tool plan only in the shadow runner |
| `entity_alias_miss` | `query_alias` | Rewrites one detected alias to a canonical simulated package |
| `retriever_rank_miss` | `retriever_weights` | Runs Hybrid RAG with explicit RRF and reranker weights |

The minimum cluster support is two cases. Single examples remain observations and cannot create a candidate.

## 4. Gates

Every candidate must satisfy:

- Configuration scope is valid.
- Linked-case score improves.
- At least two linked failures are fixed.
- Frozen regression cases introduce zero regressions.
- Core score does not decrease.
- Automatic activation is disabled.
- Human review is required.

Agent candidates replay the frozen 193-case suite. Retriever candidates replay all 30 labeled RAG cases. Shadow runs use isolated Session and Trace repositories and never update the active Policy Engine.

## 5. API and CLI

```text
POST /evolution/scan
GET  /evolution/state
POST /evolution/candidates/{candidate_id}/shadow-evaluate
POST /evolution/candidates/{candidate_id}/review
POST /evolution/candidates/{candidate_id}/activate  # always blocked
GET  /evaluation/evolution
```

```bash
python -B evaluation/eval_runner.py --suite evolution
```

## 6. Security Boundary

- No network or paid provider is used.
- Source and benchmark files are read-only inputs to the cycle.
- Candidate output is configuration data only.
- `pending_review` is the highest automatic status.
- Human approval records a decision but still leaves `active=false`.
- Runtime release remains a separate reviewed operation with Step 23 rollout and rollback controls.

## 7. Interview Wording

> I implemented an offline controlled self-evolution loop. The system mines reproducible failures from labeled benchmarks and trace outputs, clusters recurring root causes, and generates bounded Router Rule, Query Alias, or Retriever Weight candidates. Each candidate runs linked shadow cases and frozen regression suites before entering human review. In this experiment it mined 9 failures, produced 3 candidate types, fixed all 9 with zero regressions, and still blocked automatic activation. No paid API or autonomous source editing was involved.
