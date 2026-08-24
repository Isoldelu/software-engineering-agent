"""Run baseline and optimization experiments for the Agent benchmark.

The baselines are offline proxies. They make the experiment reproducible without
calling paid LLM APIs:

- DirectLLMProxy: answers from memorized package facts only, without tools.
- RAGOnlyProxy: retrieves document-like evidence and handles doc/release cases.
- Agent: runs the actual multi-tool Agent workflow.
- LegacyRouterProxy: simulates the pre-optimization keyword router without alias
  mapping or hybrid planning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = PROJECT_ROOT / "evaluation" / "large_benchmark.json"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "agent_optimization_experiment_report.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.workflow import run_agent
from app.rag.retriever import DocumentRetriever
from evaluation.eval_runner import evaluate_case, run_large_benchmark


PACKAGE_FACTS = {
    "openssl": ["openssl", "3.0.8", "1213", "libssl.so", "libcrypto.so", "deprecated API"],
    "ethtool": ["ethtool", "5.15", "1213", "extended NIC diagnostics"],
    "nginx": ["nginx", "1.24", "1214", "openssl", "HTTP performance"],
    "tcpdump": ["tcpdump", "4.99", "1214", "libpcap.so", "packet capture filter compatibility"],
}

COMPONENT_OWNERS = {
    "libssl.so": "openssl",
    "libcrypto.so": "openssl",
    "libhttp.so": "nginx",
    "libpcap.so": "tcpdump",
}


def main() -> None:
    report = run_experiment()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"wrote report to {REPORT_PATH}")


def run_experiment() -> dict:
    cases = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    direct_results = [_evaluate_proxy_case(case, _direct_llm_proxy_answer(case["query"])) for case in cases]
    rag_results = [_evaluate_proxy_case(case, _rag_only_proxy_answer(case["query"])) for case in cases]
    agent_report = run_large_benchmark()
    legacy_results = [_evaluate_legacy_router_case(case) for case in cases]

    methods = [
        _summarize_method("DirectLLMProxy", direct_results),
        _summarize_method("RAGOnlyProxy", rag_results),
        {
            "method": "Agent",
            "task_success_rate": agent_report["task_success_rate"],
            "answer_accuracy": agent_report["answer_accuracy"],
            "tool_accuracy": agent_report["tool_routing_accuracy"],
            "average_tool_calls": agent_report["average_tool_calls"]
        }
    ]
    optimization = {
        "legacy_keyword_router_tool_accuracy": _ratio(legacy_results, "tool_correct"),
        "optimized_agent_tool_accuracy": agent_report["tool_routing_accuracy"],
        "absolute_improvement": agent_report["tool_routing_accuracy"] - _ratio(legacy_results, "tool_correct")
    }

    return {
        "benchmark": "Software-Agent-Large-Bench",
        "total": len(cases),
        "summary": {
            "benchmark_cases": len(cases),
            "methods": methods,
            "optimization": optimization
        },
        "baseline_details": {
            "direct_llm_proxy": direct_results,
            "rag_only_proxy": rag_results,
            "legacy_router_proxy": legacy_results
        }
    }


def _direct_llm_proxy_answer(query: str) -> str:
    normalized = query.lower()
    for package, facts in PACKAGE_FACTS.items():
        if package in normalized:
            return " ".join(facts[:3])
    for component, owner in COMPONENT_OWNERS.items():
        if component in normalized:
            return f"{component} belongs to {owner}"
    return "No reliable answer without tools."


def _rag_only_proxy_answer(query: str) -> str:
    # Keep the historical baseline fixed; Step 20 has a separate three-mode ablation.
    retriever = DocumentRetriever(mode="legacy")
    chunks = retriever.retrieve(query, top_k=3)
    if not chunks:
        return "No relevant document evidence."
    return " ".join(chunk["content"] for chunk in chunks)


def _evaluate_proxy_case(case: dict, answer: str) -> dict:
    expected = case.get("expected_answer_contains", [])
    answer_correct = all(fragment in answer for fragment in expected)
    return {
        "category": case.get("category"),
        "query": case["query"],
        "answer_correct": answer_correct,
        "task_success": answer_correct,
        "answer": answer
    }


def _evaluate_legacy_router_case(case: dict) -> dict:
    expected_tool = case.get("expected_tool")
    expected_tools = case.get("expected_tools")
    selected_tool = _legacy_route(case["query"])
    if expected_tools:
        tool_correct = [selected_tool] == expected_tools
    else:
        tool_correct = selected_tool == expected_tool
    return {
        "category": case.get("category"),
        "query": case["query"],
        "selected_tool": selected_tool,
        "expected_tool": expected_tool,
        "expected_tools": expected_tools,
        "tool_correct": tool_correct
    }


def _legacy_route(query: str) -> str:
    normalized = query.lower()
    if any(keyword in normalized for keyword in ("document", "manual", "release note", "according to")):
        return "rag_retrieval"
    if any(keyword in normalized for keyword in ("belong", "owner", "owns", "which package")):
        return "component_mapping"
    if any(keyword in normalized for keyword in ("dependency", "dependencies", "depends", "requires", "require")):
        return "dependency_analysis"
    if any(keyword in normalized for keyword in ("compare", "changed", "change", "upgrade", "from")):
        return "version_compare"
    return "package_search"


def _summarize_method(method: str, results: list[dict]) -> dict:
    return {
        "method": method,
        "task_success_rate": _ratio(results, "task_success"),
        "answer_accuracy": _ratio(results, "answer_correct"),
        "tool_accuracy": None,
        "average_tool_calls": 0.0
    }


def _ratio(results: list[dict], key: str) -> float:
    return sum(1 for item in results if item[key]) / len(results) if results else 0.0


if __name__ == "__main__":
    main()
