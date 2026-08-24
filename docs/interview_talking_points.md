# Interview Talking Points

## 30-Second Summary

I built an AI4SE Software Engineering Agent for software asset query and analysis. It uses an Agent Router and Planner to select tools for package search, dependency analysis, version comparison, component ownership mapping, and RAG retrieval. The system supports hybrid multi-tool tasks, records execution trajectories, and includes benchmark, bad-case, robustness, and baseline experiments.

## Project Motivation

Software engineering data is often scattered across package metadata, dependency records, version changes, release notes, and manuals. A normal RAG system is weak for structured package/dependency/version questions, while a pure rule-based tool system is weak for natural-language intent. This project combines Agent planning, deterministic tools, and RAG evidence retrieval.

## What I Built

- Simulated software asset knowledge base
- Five Agent tools
- Router and Hybrid Planner
- RAG retriever
- Trajectory logging
- FastAPI service
- Browser demo
- Evaluation dashboard
- Large benchmark and baseline experiment

## Important Technical Points

Tool system:

```text
PackageSearchTool
DependencyAnalysisTool
VersionCompareTool
ComponentMappingTool
RAGRetrieverTool
```

Hybrid planning example:

```text
1214 release packages and their dependencies
-> RAGRetrieverTool
-> PackageSearchTool
-> DependencyAnalysisTool
```

Robustness example:

```text
查一下 nginx 的版本变化和依赖
-> PackageSearchTool
-> DependencyAnalysisTool
-> VersionCompareTool
```

## Experiment Story

I first built a small benchmark, then added bad-case and robustness suites. Later I expanded evaluation to 170 large-benchmark cases across six task types. I compared DirectLLMProxy, RAGOnlyProxy, and Agent. Agent performed best because it can select structured tools and compose multi-step workflows.

Results:

```text
DirectLLMProxy task_success: 22.94%
RAGOnlyProxy task_success: 57.06%
Agent task_success: 100.00%
```

Optimization:

```text
Legacy keyword router tool_accuracy: 61.76%
Optimized Agent tool_accuracy: 100.00%
```

## How To Explain Compliance

This project does not use internal enterprise data. It is a personal reproduction of the methodology using simulated software asset data. The professional experience and the personal demo should be described separately:

```text
Professional experience:
Participated in software asset retrieval, parsing automation, and Agent tool exploration in a network device R&D environment.

Personal reproduction project:
Built a simulated-data Software Engineering Agent prototype to validate Agent methodology.
```

## Likely Interview Questions

Q: Is this just keyword matching?

A: The first version had keyword routing, but later I added alias mapping, hybrid planning, tool argument normalization, reverse dependency support, and robustness evaluation. I also compared a legacy keyword router with the optimized Agent, improving tool accuracy from 61.76% to 100%.

Q: Why not just use RAG?

A: RAG works well for unstructured documents, but package/dependency/version/component tasks require structured tools. In the experiment, RAGOnlyProxy reached 57.06% task success, while the Agent reached 100% on the simulated benchmark because it combines structured tools with retrieval.

Q: Did you use real LLM API?

A: The current project is designed to be reproducible without paid tokens. It uses deterministic local routing and offline proxy baselines, while preserving prompt and function schema layers for future LLM Router or Function Calling integration.

Q: How did you make the multi-Worker service operable?

A: I added checksum-protected SQL migrations with a PostgreSQL advisory lock, revision CAS and TTL leases for consistency, and database-managed role Keys whose hashes are shared across Workers. Key rotation supports a grace window and creates redacted Audit events. Session, Trace, Feedback, Evolution, and Audit records have configurable bounded retention. In local two-Worker acceptance, 60 concurrent requests completed with zero server errors; after terminating one Worker, Uvicorn replaced it and a 40-request recovery run also completed without errors. Real PostgreSQL load and database outage recovery are executable CI gates, so I distinguish implemented CI coverage from locally executed results.

Q: How do you observe and recover the control plane?

A: Each PostgreSQL Worker owns a bounded psycopg pool, while Prometheus uses its multiprocess mode to aggregate request, latency, denial, retention, audit-failure, storage, and pool metrics without putting queries or IDs in labels. Audit is dual-written to the database and a filtered JSONL outlet; the outlet is still attempted when the database insert fails. For recovery, I built a SHA-256 logical backup with pre-restore verification and a database restore lease. The local drill restored 2/2 records and rejected corruption. CI is configured to retain all PostgreSQL evidence as an artifact, but I do not claim that run as completed because this local folder has no GitHub remote or credentials.
