# Experiment Results

## Benchmark Suites

| Suite | Cases | Tool Routing | Task Success | Grounding | Answer Accuracy | Bad Cases |
|---|---:|---:|---:|---:|---:|---:|
| Software-Agent-Bench | 12 | 100.00% | 100.00% | 100.00% | 100.00% | 0 |
| Software-Agent-Challenge | 5 | 100.00% | 100.00% | 100.00% | 100.00% | 0 |
| Software-Agent-Robustness | 6 | 100.00% | 100.00% | 100.00% | 100.00% | 0 |
| Software-Agent-Large-Bench | 170 | 100.00% | 100.00% | 100.00% | 100.00% | 0 |

## Large Benchmark Distribution

| Category | Count |
|---|---:|
| package_query | 30 |
| dependency | 30 |
| version_compare | 30 |
| component_mapping | 20 |
| rag_query | 30 |
| hybrid_task | 30 |
| total | 170 |

## Baseline Comparison

The baselines are offline proxy baselines for reproducibility. They do not call paid LLM APIs.

| Method | Task Success | Answer Accuracy | Tool Accuracy |
|---|---:|---:|---:|
| DirectLLMProxy | 22.94% | 22.94% | N/A |
| RAGOnlyProxy | 57.06% | 57.06% | N/A |
| Agent | 100.00% | 100.00% | 100.00% |

## Optimization Experiment

| Method | Tool Accuracy |
|---|---:|
| LegacyKeywordRouter | 61.76% |
| OptimizedAgent | 100.00% |

Absolute improvement:

```text
+38.24%
```

## Bad Cases Found And Fixed

The large benchmark exposed concentrated bad cases:

- `what release contains nginx` was routed to RAG or component mapping.
- `secure communication library package info` did not pass normalized package arguments to `PackageSearchTool`.
- `1213 release packages and their dependencies` failed because `ethtool` had no explicit empty dependency record.
- `contains` created ambiguity between release containment and component ownership.

Fixes:

- Added package metadata priority rules.
- Added release contains priority rules.
- Passed normalized package/release arguments to tool execution.
- Added an explicit empty dependency record for `ethtool`.
- Resolved `contains` routing ambiguity.

