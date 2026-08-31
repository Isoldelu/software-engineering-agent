# Resume Version

## Project Title

AI Software Engineering Agent: Multi-Tool Agent for Software Asset Retrieval and Analysis

## Project Description

Built a Software Engineering Agent for R&D scenarios where package metadata, dependencies, version changes, component ownership, and release documents are distributed across multiple sources. The system uses Agent routing, tool calling, RAG retrieval, hybrid planning, trajectory logging, and benchmark evaluation to support natural-language software asset query and analysis.

## Responsibilities

- Built a simulated software asset knowledge base with package, dependency, version, component, release-note, and manual data.
- Implemented specialized Agent tools including package search, dependency analysis, version comparison, component ownership mapping, and RAG retrieval.
- Designed a Router and Hybrid Planner to select tools and compose multi-step workflows for complex engineering queries.
- Added replayable Trace, structured Evidence/Citation, deterministic verification, and partial-success semantics for debugging and trustworthy answers.
- Built benchmark, challenge, robustness, and large-scale experiment suites with 193 total evaluation cases.
- Compared DirectLLMProxy, RAGOnlyProxy, and Agent baselines; Agent achieved 100% task success on the simulated large benchmark.
- Improved tool routing accuracy from 61.76% to 100% by analyzing bad cases and adding alias mapping, planner rules, and tool argument normalization.
- Built a controlled Feedback and policy loop with shadow evaluation, human review, deterministic gray rollout, and rollback.
- Exposed the system through FastAPI and PostgreSQL with multi-Worker state, role-aware authentication, Audit, Prometheus, retention, and backup/restore.

## Resume Bullets

- Designed and implemented a multi-tool Software Engineering Agent for software asset retrieval and analysis, supporting package lookup, dependency reasoning, version comparison, component ownership mapping, and RAG-based document retrieval.
- Built a Hybrid Planner to decompose complex engineering queries into multi-tool chains, with Evidence/Citation, deterministic verification, partial-success handling, and replayable Trace.
- Constructed benchmark, challenge, robustness, and large-scale evaluation suites covering 193 simulated cases across six task categories.
- Designed offline baseline experiments comparing DirectLLMProxy, RAGOnlyProxy, and Agent; Agent achieved 100% task success on the simulated large benchmark.
- Improved tool routing accuracy from 61.76% to 100% through bad-case analysis, alias mapping, planner optimization, and normalized tool arguments; configuration candidates require frozen-set replay and human review.
- Delivered FastAPI/PostgreSQL multi-Worker operations with CAS/Lease consistency, Auth/Audit/Metrics and recovery gates; GitHub CI passed 150 tests, 100/100 initial requests, and 40/40 requests after Worker replacement with zero server errors.
