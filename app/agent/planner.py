"""Hybrid Agent planner.

The planner turns a user query into one or more tool steps. It is still
deterministic, but the shape mirrors an LLM planning output:

task understanding -> tool sequence -> execution arguments
"""

from __future__ import annotations

from app.agent.llm_router import parse_llm_plan
from app.agent.prompt import build_planner_prompt
from app.agent.router import (
    DEPENDENCY_KEYWORDS,
    RAG_RETRIEVAL_KEYWORDS,
    VERSION_COMPARE_KEYWORDS,
    extract_package,
    extract_release,
    route_query_detail,
)


def build_plan(query: str, llm_output: str | None = None) -> dict:
    """Build a single-tool or multi-tool execution plan."""
    if llm_output:
        parsed = parse_llm_plan(query, llm_output)
        if parsed["valid"]:
            return parsed["plan"]

    normalized = query.lower()
    package = extract_package(normalized)
    release = extract_release(normalized)

    if _is_package_dependency_version_question(query, normalized, package, release):
        return {
            "intent": "hybrid_package_dependency_version_analysis",
            "tool": "hybrid_plan",
            "arguments": {
                "package": package,
                "release": release
            },
            "confidence": "high",
            "reason": "The query asks for both dependency analysis and version changes.",
            "planner_prompt": build_planner_prompt(query),
            "planner_fallback": "deterministic_rule",
            "steps": [
                {
                    "tool": "package_search",
                    "arguments": {"query": query},
                    "reason": "Resolve package metadata before running analysis tools."
                },
                {
                    "tool": "dependency_analysis",
                    "arguments": {"package": package, "from_previous_packages": package is None},
                    "reason": "Analyze dependencies for the resolved package."
                },
                {
                    "tool": "version_compare",
                    "arguments": {"package": package, "from_previous_packages": package is None},
                    "reason": "Compare version changes for the resolved package."
                }
            ]
        }

    if _is_release_dependency_question(query, normalized, release):
        return {
            "intent": "hybrid_release_dependency_analysis",
            "tool": "hybrid_plan",
            "arguments": {
                "package": package,
                "release": release
            },
            "confidence": "high",
            "reason": "The query needs release/document evidence plus package dependency analysis.",
            "planner_prompt": build_planner_prompt(query),
            "planner_fallback": "deterministic_rule",
            "steps": [
                {
                    "tool": "rag_retrieval",
                    "arguments": {"query": query},
                    "reason": "Retrieve release note evidence for the requested release."
                },
                {
                    "tool": "package_search",
                    "arguments": {"query": query},
                    "reason": "Find packages associated with the requested release or package."
                },
                {
                    "tool": "dependency_analysis",
                    "arguments": {"package": package, "from_previous_packages": package is None},
                    "reason": "Analyze dependencies for the target package or release packages."
                }
            ]
        }

    if _is_release_version_question(query, normalized, release):
        return {
            "intent": "hybrid_release_version_compare",
            "tool": "hybrid_plan",
            "arguments": {
                "package": package,
                "release": release
            },
            "confidence": "high",
            "reason": "The query needs release/package lookup before comparing package version changes.",
            "planner_prompt": build_planner_prompt(query),
            "planner_fallback": "deterministic_rule",
            "steps": [
                {
                    "tool": "rag_retrieval",
                    "arguments": {"query": query},
                    "reason": "Retrieve release note evidence for the requested release."
                },
                {
                    "tool": "package_search",
                    "arguments": {"query": query},
                    "reason": "Find packages associated with the requested release or package."
                },
                {
                    "tool": "version_compare",
                    "arguments": {"package": package, "from_previous_packages": package is None},
                    "reason": "Compare version changes for the target package or release packages."
                }
            ]
        }

    route = route_query_detail(query)
    return {
        **route,
        "planner_prompt": build_planner_prompt(query),
        "planner_fallback": "deterministic_rule",
        "steps": [
            {
                "tool": route["tool"],
                "arguments": {**route.get("arguments", {}), "query": query},
                "reason": route["reason"]
            }
        ]
    }


def _is_release_dependency_question(query: str, normalized: str, release: str | None) -> bool:
    asks_dependency = any(keyword in query or keyword in normalized for keyword in DEPENDENCY_KEYWORDS)
    asks_docs_or_release = (
        release is not None
        or any(keyword in query or keyword in normalized for keyword in RAG_RETRIEVAL_KEYWORDS)
    )
    return asks_dependency and asks_docs_or_release


def _is_release_version_question(query: str, normalized: str, release: str | None) -> bool:
    asks_version = any(keyword in query or keyword in normalized for keyword in VERSION_COMPARE_KEYWORDS)
    asks_docs_or_release = (
        release is not None
        or any(keyword in query or keyword in normalized for keyword in RAG_RETRIEVAL_KEYWORDS)
    )
    return asks_version and asks_docs_or_release


def _is_package_dependency_version_question(
    query: str,
    normalized: str,
    package: str | None,
    release: str | None
) -> bool:
    asks_dependency = any(keyword in query or keyword in normalized for keyword in DEPENDENCY_KEYWORDS)
    asks_version = any(keyword in query or keyword in normalized for keyword in VERSION_COMPARE_KEYWORDS)
    return release is None and package is not None and asks_dependency and asks_version
