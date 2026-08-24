"""Evaluation runner for the Software-Agent benchmark and bad-case loop."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_CASES_PATH = PROJECT_ROOT / "evaluation" / "test_cases.json"
CHALLENGE_CASES_PATH = PROJECT_ROOT / "evaluation" / "challenge_cases.json"
ROBUSTNESS_CASES_PATH = PROJECT_ROOT / "evaluation" / "robustness_cases.json"
LARGE_BENCHMARK_PATH = PROJECT_ROOT / "evaluation" / "large_benchmark.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.workflow import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Software-Agent evaluation suites.")
    parser.add_argument(
        "--suite",
        choices=["benchmark", "challenge", "robustness", "large", "experiment", "evidence", "verifier", "rag", "context", "feedback", "policy", "provider", "evolution", "control-plane", "all"],
        default="benchmark",
        help="Evaluation suite to run."
    )
    args = parser.parse_args()

    if args.suite == "control-plane":
        report = run_control_plane_evaluation()
    elif args.suite == "evolution":
        report = run_evolution_evaluation()
    elif args.suite == "provider":
        report = run_provider_evaluation()
    elif args.suite == "policy":
        report = run_policy_evaluation()
    elif args.suite == "feedback":
        report = run_feedback_loop_evaluation()
    elif args.suite == "context":
        report = run_context_evaluation()
    elif args.suite == "rag":
        report = run_rag_evaluation()
    elif args.suite == "verifier":
        report = run_verifier_evaluation()
    elif args.suite == "evidence":
        report = run_evidence_evaluation()
    elif args.suite == "challenge":
        report = run_bad_case_analysis()
    elif args.suite == "robustness":
        report = run_robustness_evaluation()
    elif args.suite == "large":
        report = run_large_benchmark()
    elif args.suite == "experiment":
        report = run_benchmark_experiment()
    elif args.suite == "all":
        report = run_all_evaluations()
    else:
        report = run_evaluation()
    print(json.dumps(report, ensure_ascii=False, indent=2))


def run_evaluation(
    test_cases_path: Path = TEST_CASES_PATH,
    suite_name: str = "Software-Agent-Bench"
) -> dict:
    """Run an evaluation suite and return a structured report."""
    test_cases = json.loads(test_cases_path.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in test_cases]
    total = len(results)
    bad_cases = [item for item in results if item["bad_case_reason"]]

    return {
        "benchmark": suite_name,
        "total": total,
        "tool_routing_accuracy": _ratio(results, "tool_correct"),
        "task_success_rate": _ratio(results, "task_success"),
        "answer_grounding_accuracy": _ratio(results, "answer_grounded"),
        "answer_accuracy": _ratio(results, "answer_correct"),
        "average_tool_calls": (
            sum(item["tool_call_count"] for item in results) / total if total else 0.0
        ),
        "bad_cases": bad_cases,
        "results": results
    }


def run_bad_case_analysis() -> dict:
    """Run challenge cases and return failure taxonomy plus optimization hints."""
    report = run_evaluation(CHALLENGE_CASES_PATH, "Software-Agent-Challenge")
    bad_case_types = Counter(
        item["bad_case_reason"] for item in report["bad_cases"] if item["bad_case_reason"]
    )
    report["bad_case_count"] = len(report["bad_cases"])
    report["bad_case_types"] = dict(bad_case_types)
    report["optimization_suggestions"] = _build_optimization_suggestions(
        report["bad_cases"],
        bad_case_types
    )
    return report


def run_robustness_evaluation() -> dict:
    """Run ambiguous-query robustness cases."""
    report = run_evaluation(ROBUSTNESS_CASES_PATH, "Software-Agent-Robustness")
    bad_case_types = Counter(
        item["bad_case_reason"] for item in report["bad_cases"] if item["bad_case_reason"]
    )
    report["bad_case_count"] = len(report["bad_cases"])
    report["bad_case_types"] = dict(bad_case_types)
    report["optimization_suggestions"] = _build_optimization_suggestions(
        report["bad_cases"],
        bad_case_types
    )
    return report


def run_large_benchmark() -> dict:
    """Run the larger Agent benchmark for optimization experiments."""
    return run_evaluation(LARGE_BENCHMARK_PATH, "Software-Agent-Large-Bench")


def run_benchmark_experiment() -> dict:
    """Run baseline and optimization experiment."""
    from evaluation.experiment_runner import run_experiment

    return run_experiment()


def run_evidence_evaluation() -> dict:
    """Run Step 18 Evidence normalization and Citation coverage evaluation."""
    from evaluation.evidence_eval import run_evidence_evaluation as run

    return run()


def run_verifier_evaluation() -> dict:
    """Run Step 19 injected-error and false-rejection evaluation."""
    from evaluation.verifier_eval import run_verifier_evaluation as run

    return run()


def run_rag_evaluation() -> dict:
    """Run Step 20 labeled retrieval and ablation evaluation."""
    from evaluation.rag_eval import run_rag_evaluation as run

    return run()


def run_context_evaluation() -> dict:
    """Run Step 21 multi-turn Context and enhanced Trace evaluation."""
    from evaluation.context_eval import run_context_evaluation as run

    return run()


def run_feedback_loop_evaluation() -> dict:
    """Run Step 22 controlled Feedback and candidate replay evaluation."""
    from evaluation.feedback_loop_eval import run_feedback_loop_evaluation as run

    return run()


def run_policy_evaluation() -> dict:
    """Run Step 23 policy versioning, rollout, and rollback evaluation."""
    from evaluation.policy_eval import run_policy_evaluation as run

    return run()


def run_provider_evaluation() -> dict:
    """Run Step 24 offline/online provider and fallback evaluation."""
    from evaluation.provider_eval import run_provider_evaluation as run

    return run()


def run_evolution_evaluation() -> dict:
    """Run Step 25 offline failure mining and shadow candidate evaluation."""
    from evaluation.evolution_eval import run_evolution_evaluation as run

    return run()


def run_control_plane_evaluation() -> dict:
    """Run Step 26 persistence, authorization, and consistency evaluation."""
    from evaluation.control_plane_eval import run_control_plane_evaluation as run

    return run()


def run_all_evaluations() -> dict:
    """Run all evaluation suites."""
    return {
        "benchmark": run_evaluation(),
        "bad_case_loop": run_bad_case_analysis(),
        "robustness": run_robustness_evaluation(),
        "large_benchmark": run_large_benchmark(),
        "benchmark_experiment": run_benchmark_experiment(),
        "hybrid_rag": run_rag_evaluation(),
        "context_trace": run_context_evaluation(),
        "controlled_feedback": run_feedback_loop_evaluation(),
        "policy_rollout": run_policy_evaluation(),
        "provider_dual_mode": run_provider_evaluation(),
        "offline_evolution": run_evolution_evaluation(),
        "control_plane": run_control_plane_evaluation(),
    }


def run_evaluation_summary() -> dict:
    """Return a compact interview-friendly summary across all suites."""
    suites = run_all_evaluations()
    suite_summaries = [
        _summarize_suite(key, report)
        for key, report in suites.items()
        if "tool_routing_accuracy" in report
    ]
    total_cases = sum(item["total"] for item in suite_summaries)
    total_bad_cases = sum(item["bad_case_count"] for item in suite_summaries)

    return {
        "project": "AI Software Engineering Agent",
        "summary": {
            "suite_count": len(suite_summaries),
            "total_cases": total_cases,
            "total_bad_cases": total_bad_cases,
            "all_suites_passed": total_bad_cases == 0,
            "average_tool_routing_accuracy": _average_metric(suite_summaries, "tool_routing_accuracy"),
            "average_task_success_rate": _average_metric(suite_summaries, "task_success_rate"),
            "average_answer_grounding_accuracy": _average_metric(suite_summaries, "answer_grounding_accuracy"),
            "average_answer_accuracy": _average_metric(suite_summaries, "answer_accuracy")
        },
        "suites": suite_summaries,
        "experiment": suites["benchmark_experiment"]["summary"],
        "interview_highlights": [
            "Standard benchmark validates the core Agent tool-calling path.",
            "Challenge suite validates the bad-case optimization loop.",
            "Robustness suite validates ambiguous engineering-style queries.",
            "Large benchmark compares DirectLLMProxy, RAGOnlyProxy, and Agent.",
            "Hybrid RAG compares legacy overlap, BM25, and RRF plus deterministic reranking.",
            "Context/Trace evaluation validates multi-turn inheritance, isolation, and replay.",
            "Controlled Feedback creates configuration candidates with replay and human review gates.",
            "Policy evaluation validates stable rollout assignment and source-free rollback.",
            "Provider evaluation validates optional online planning and deterministic fallback.",
            "Offline evolution mines failures, clusters root causes, and shadow-tests safe candidates.",
            "Control-plane evaluation validates persistence, API roles, CAS, and database leases.",
            "Evaluation includes routing, task success, grounding, answer accuracy, and tool-call efficiency."
        ]
    }


def evaluate_case(case: dict) -> dict:
    result = run_agent(case["query"], persist_trajectory=False)
    expected_fragments = case.get("expected_answer_contains", [])
    expected_status = case.get("expected_status", "success")
    tool_correct = _tool_correct(result, case)
    task_success = _task_success(result, expected_status)
    answer_correct = all(fragment in result["answer"] for fragment in expected_fragments)
    answer_grounded = _is_answer_grounded(result, expected_fragments, expected_status)

    return {
        "query": case["query"],
        "selected_tool": result["selected_tool"],
        "used_tools": result.get("used_tools", []),
        "expected_tool": case.get("expected_tool"),
        "expected_tools": case.get("expected_tools"),
        "expected_status": expected_status,
        "tool_correct": tool_correct,
        "task_success": task_success,
        "answer_correct": answer_correct,
        "answer_grounded": answer_grounded,
        "tool_call_count": result.get("tool_call_count", len(result.get("used_tools", []))),
        "answer": result["answer"],
        "evidence": result.get("evidence", []),
        "expected_answer_contains": expected_fragments,
        "bad_case_reason": _bad_case_reason(
            tool_correct,
            task_success,
            answer_grounded,
            answer_correct
        )
    }


def _tool_correct(result: dict, case: dict) -> bool:
    if "expected_tools" in case:
        return result.get("used_tools", []) == case["expected_tools"]
    return result["selected_tool"] == case["expected_tool"]


def _task_success(result: dict, expected_status: str) -> bool:
    if expected_status == "not_found":
        return _has_observation_status(result, "not_found")
    if expected_status == "partial_success":
        return result.get("success", False) or _has_observation_status(result, "success")
    return result.get("success", False)


def _is_answer_grounded(
    result: dict,
    expected_fragments: list[str],
    expected_status: str = "success"
) -> bool:
    if expected_status != "not_found" and (not result.get("success") or not result.get("evidence")):
        return False
    evidence_text = json.dumps(result.get("trajectory", []), ensure_ascii=False)
    return all(fragment in evidence_text for fragment in expected_fragments)


def _has_observation_status(result: dict, status: str) -> bool:
    for item in result.get("trajectory", []):
        observation = item.get("observation", {})
        if observation.get("status") == status:
            return True
    return False


def _bad_case_reason(
    tool_correct: bool,
    task_success: bool,
    answer_grounded: bool,
    answer_correct: bool
) -> str | None:
    if not tool_correct:
        return "wrong_tool"
    if not task_success:
        return "tool_execution_failed"
    if not answer_grounded:
        return "answer_not_grounded"
    if not answer_correct:
        return "answer_missing_expected_content"
    return None


def _build_optimization_suggestions(
    bad_cases: list[dict],
    bad_case_types: Counter
) -> list[dict]:
    """Convert bad-case reasons into concrete next optimization actions."""
    suggestions = []
    if bad_case_types.get("wrong_tool"):
        suggestions.append({
            "reason": "wrong_tool",
            "count": bad_case_types["wrong_tool"],
            "action": "Add Router/Planner rules or few-shot examples for ambiguous queries."
        })
    if bad_case_types.get("tool_execution_failed"):
        suggestions.append({
            "reason": "tool_execution_failed",
            "count": bad_case_types["tool_execution_failed"],
            "action": "Expand the simulated knowledge base or add a fallback path for missing records."
        })
    if bad_case_types.get("answer_not_grounded"):
        suggestions.append({
            "reason": "answer_not_grounded",
            "count": bad_case_types["answer_not_grounded"],
            "action": "Tighten answer generation so every key answer fragment is traceable to evidence."
        })
    if bad_case_types.get("answer_missing_expected_content"):
        suggestions.append({
            "reason": "answer_missing_expected_content",
            "count": bad_case_types["answer_missing_expected_content"],
            "action": "Improve answer templates or tool fields to avoid omitting expected facts."
        })

    if not bad_cases:
        suggestions.append({
            "reason": "none",
            "count": 0,
            "action": "The current challenge suite passes; add longer and more ambiguous engineering queries next."
        })
    return suggestions


def _ratio(results: list[dict], key: str) -> float:
    total = len(results)
    return sum(1 for item in results if item[key]) / total if total else 0.0


def _summarize_suite(key: str, report: dict) -> dict:
    return {
        "key": key,
        "benchmark": report["benchmark"],
        "total": report["total"],
        "tool_routing_accuracy": report["tool_routing_accuracy"],
        "task_success_rate": report["task_success_rate"],
        "answer_grounding_accuracy": report["answer_grounding_accuracy"],
        "answer_accuracy": report["answer_accuracy"],
        "average_tool_calls": report["average_tool_calls"],
        "bad_case_count": len(report["bad_cases"]),
        "passed": len(report["bad_cases"]) == 0
    }


def _average_metric(suites: list[dict], key: str) -> float:
    return sum(item[key] for item in suites) / len(suites) if suites else 0.0


if __name__ == "__main__":
    main()
