# Step 25 Offline Controlled Evolution Report

## Result

```text
Mode: offline_controlled
Paid API calls: 0
Mined failures: 9
Root-cause clusters: 3
Configuration candidates: 3
Fixed linked bad cases: 9
Regressed cases: 0
Final automatic status: pending_review
Automatic activation: blocked
```

## Candidate Comparison

| Candidate | Linked baseline | Shadow candidate | Fixed | Regression suite | Regressions |
|---|---:|---:|---:|---:|---:|
| Query Alias: `tls toolkit -> openssl` | 0% | 100% | 2 | 193 | 0 |
| Retriever Weights: Hybrid RAG | 0% | 100% | 4 | 30 | 0 |
| Router Rule: `prerequisites -> dependency_analysis` | 0% | 100% | 3 | 193 | 0 |

The Retriever candidate also improves the 30-case core score from 86.67% to 100%. Agent candidates keep the 193-case core score at 100%.

## Root Causes

- `router_miss`: `prerequisites` was not represented by the deterministic dependency Router.
- `entity_alias_miss`: `tls toolkit` was not mapped to the simulated `openssl` package.
- `retriever_rank_miss`: Legacy overlap retrieval missed four Chinese semantic queries that Hybrid RAG retrieves.

## Interpretation

This result demonstrates candidate discovery and verification, not autonomous deployment. All three candidates stop at `pending_review`; approval also keeps `active=false`. Production policy changes must still use the reviewed Step 23 versioning, rollout, monitoring, and rollback path.
