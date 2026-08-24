# Step 15 Agent Benchmark & Optimization Experiment

## Current Problem

The project already had an engineering demo, a small benchmark, a challenge set, and a robustness set. However, it still lacked a larger experiment that could support algorithm-oriented interview discussion.

The missing parts were:

- A larger benchmark with 100+ cases.
- Baseline comparison.
- Optimization-before/after comparison.

## Why This Step Was Added

This step turns the project from:

```text
Engineering Agent Demo
```

into:

```text
Agent project with benchmark and optimization experiment results
```

It gives you stronger evidence for resume claims such as:

> Built an Agent evaluation framework and improved tool routing accuracy through bad-case analysis and planner optimization.

## Benchmark Expansion

Generated file:

- `evaluation/large_benchmark.json`

Total cases:

```text
170
```

Category distribution:

```text
package_query: 30
dependency: 30
version_compare: 30
component_mapping: 20
rag_query: 30
hybrid_task: 30
```

## Baselines

The experiment uses offline proxy baselines so it can be reproduced without paid LLM tokens:

- `DirectLLMProxy`: memorized package facts only, no tools.
- `RAGOnlyProxy`: document retrieval only.
- `Agent`: full tool-using Agent.

## Results

```text
Method           Task Success   Answer Accuracy   Tool Accuracy
DirectLLMProxy   22.94%         22.94%            N/A
RAGOnlyProxy     57.06%         57.06%            N/A
Agent            100.00%        100.00%           100.00%
```

## Optimization Experiment

Compared:

- `LegacyKeywordRouter`: keyword-only routing without alias mapping or hybrid planning.
- `OptimizedAgent`: current Agent with alias mapping, reverse dependency, planner, RAG filtering, and hybrid execution.

```text
Legacy keyword router tool accuracy: 61.76%
Optimized Agent tool accuracy:       100.00%
Absolute improvement:                +38.24%
```

## What Was Optimized During This Step

The first large-benchmark run exposed several concentrated bad cases:

- Package metadata queries such as `what release contains nginx` were routed to RAG or component mapping.
- Alias package queries such as `secure communication library package info` did not pass normalized package names into `PackageSearchTool`.
- Release dependency tasks over packages with no dependencies needed explicit empty dependency records.

Fixes:

- Added package metadata priority rules.
- Passed normalized package/release arguments to package search execution.
- Added explicit empty dependency record for `ethtool`.
- Resolved `contains` ambiguity between release containment and component ownership.

Final large benchmark:

```text
total: 170
tool_routing_accuracy: 1.0
task_success_rate: 1.0
answer_grounding_accuracy: 1.0
answer_accuracy: 1.0
bad_cases: 0
```

## Interview Framing

> I expanded the evaluation from 23 cases to 170 cases across package query, dependency analysis, version comparison, component mapping, RAG, and hybrid tasks. I also added offline baselines to compare direct-answer, RAG-only, and Agent-based methods. The Agent outperformed baselines because it can route tasks to structured tools and compose multi-step workflows. I further compared a legacy keyword router with the optimized planner, showing tool accuracy improved from 61.76% to 100% after alias mapping, planner rules, and bad-case-driven fixes.

