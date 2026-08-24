# Resume Version

## Project Title

AI Software Engineering Agent: Multi-Tool Agent for Software Asset Retrieval and Analysis

## Project Description

Built a Software Engineering Agent for R&D scenarios where package metadata, dependencies, version changes, component ownership, and release documents are distributed across multiple sources. The system uses Agent routing, tool calling, RAG retrieval, hybrid planning, trajectory logging, and benchmark evaluation to support natural-language software asset query and analysis.

## Responsibilities

- Built a simulated software asset knowledge base with package, dependency, version, component, release-note, and manual data.
- Implemented specialized Agent tools including package search, dependency analysis, version comparison, component ownership mapping, and RAG retrieval.
- Designed a Router and Hybrid Planner to select tools and compose multi-step workflows for complex engineering queries.
- Added trajectory logging and structured evidence output for debugging, evaluation, and bad-case analysis.
- Built benchmark, challenge, robustness, and large-scale experiment suites with 193 total evaluation cases.
- Compared DirectLLMProxy, RAGOnlyProxy, and Agent baselines; Agent achieved 100% task success on the simulated large benchmark.
- Improved tool routing accuracy from 61.76% to 100% by analyzing bad cases and adding alias mapping, planner rules, and tool argument normalization.
- Exposed the system through FastAPI APIs, a browser Agent demo, and an evaluation dashboard.

## Resume Bullets

- Designed and implemented a multi-tool Software Engineering Agent for software asset retrieval and analysis, supporting package lookup, dependency reasoning, version comparison, component ownership mapping, and RAG-based document retrieval.
- Built a Hybrid Planner to decompose complex engineering queries into tool chains such as `RAG -> PackageSearch -> DependencyAnalysis`, with trajectory logging and evidence-grounded answer generation.
- Constructed benchmark, challenge, robustness, and large-scale evaluation suites covering 193 simulated cases across six task categories.
- Designed offline baseline experiments comparing DirectLLMProxy, RAGOnlyProxy, and Agent; Agent achieved 100% task success on the simulated large benchmark.
- Improved tool routing accuracy from 61.76% to 100% through bad-case analysis, alias mapping, planner optimization, and normalized tool argument passing.

