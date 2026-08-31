"""Prompt and tool schema definitions.

This module documents the prompt layer that a real LLM Router or LangGraph
function-calling workflow can reuse. The current demo still uses deterministic
planning, but the schemas here make the tool interface explicit and interview
ready.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are an AI4SE Agent for network device software engineering.
Use tools to verify package metadata, dependency relationships, version changes,
component ownership, and engineering document evidence. Do not guess. Prefer
structured tool observations over unsupported natural-language assumptions."""


TOOL_SCHEMAS = [
    {
        "name": "package_search",
        "description": "Search package metadata by package name or release id.",
        "inputs": {
            "query": "Natural-language query containing a package name or release id."
        },
        "outputs": [
            "package metadata",
            "release package list",
            "evidence path"
        ]
    },
    {
        "name": "dependency_analysis",
        "description": "Analyze direct dependencies for a package.",
        "inputs": {
            "query": "Natural-language query containing a package name."
        },
        "outputs": [
            "package",
            "dependencies",
            "dependency tree",
            "evidence path"
        ]
    },
    {
        "name": "version_compare",
        "description": "Compare simulated old and new package versions.",
        "inputs": {
            "query": "Natural-language query containing a package name and version-comparison intent."
        },
        "outputs": [
            "old version",
            "new version",
            "changes",
            "evidence path"
        ]
    },
    {
        "name": "component_mapping",
        "description": "Map a component or file, such as libssl.so, to its owning package.",
        "inputs": {
            "query": "Natural-language query containing a component or file name."
        },
        "outputs": [
            "component",
            "owning packages",
            "evidence path"
        ]
    },
    {
        "name": "rag_retrieval",
        "description": "Retrieve release note or software manual evidence.",
        "inputs": {
            "query": "Natural-language query asking about release notes, manuals, or document evidence."
        },
        "outputs": [
            "matched document chunks",
            "scores",
            "matched terms",
            "source paths"
        ]
    }
]


PLANNER_OUTPUT_FORMAT = {
    "intent": "task intent",
    "tool": "single tool name or hybrid_plan",
    "arguments": {"query": "original or focused natural-language query"},
    "confidence": "low, medium, or high",
    "reason": "short reason for the selected plan",
    "steps": [
        {
            "tool": "tool name",
            "arguments": {"query": "natural-language query for this tool"},
            "reason": "why this tool is needed"
        }
    ]
}

PLANNER_RULES = [
    "Return one JSON object only, without markdown or extra text.",
    "The top-level arguments and every step arguments value must be JSON objects.",
    "Use exactly one step for a single intent and set tool to that step tool.",
    "Use hybrid_plan only when the user explicitly asks for multiple intents or sources.",
    "A current package version lookup uses package_search, not version_compare.",
    "Use version_compare only for change, difference, history, old/new, or compare intent.",
    (
        "For release packages followed by dependency or version analysis, call package_search "
        "first, then set from_previous_packages to true in the downstream step arguments."
    ),
    (
        "When the query explicitly cites a release note or manual, include rag_retrieval; "
        "a release id alone does not require document retrieval."
    ),
    "Do not add speculative tools. Prefer the smallest sufficient plan.",
]


def build_planner_prompt(query: str) -> str:
    """Build a planner prompt for future LLM Router integration."""
    return "\n\n".join([
        SYSTEM_PROMPT,
        "Available tools:",
        json.dumps(TOOL_SCHEMAS, ensure_ascii=False, indent=2),
        "Planner rules:",
        "\n".join(f"- {rule}" for rule in PLANNER_RULES),
        "Return a JSON plan in this format:",
        json.dumps(PLANNER_OUTPUT_FORMAT, ensure_ascii=False, indent=2),
        f"User query: {query}"
    ])


def export_tool_schemas() -> list[dict]:
    """Return tool schemas for LangGraph or function-calling integration."""
    return TOOL_SCHEMAS
