"""Injected-error and false-rejection evaluation for the Step 19 Verifier."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_CASES_PATH = PROJECT_ROOT / "evaluation" / "verifier_cases.json"
LEGITIMATE_CASE_PATHS = [
    PROJECT_ROOT / "evaluation" / "test_cases.json",
    PROJECT_ROOT / "evaluation" / "challenge_cases.json",
    PROJECT_ROOT / "evaluation" / "robustness_cases.json",
    PROJECT_ROOT / "evaluation" / "large_benchmark.json",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.planner import build_plan
from app.agent.verifier import DeterministicVerifier, aggregate_execution_status
from app.agent.workflow import (
    _extract_evidence_items,
    execute_plan,
    generate_final_answer,
    run_agent,
)
from app.evidence.models import Citation, Evidence
from app.evidence.normalizer import citations_from_evidence


PARTIAL_PLAN = {
    "intent": "hybrid_partial_demo",
    "tool": "hybrid_plan",
    "arguments": {},
    "confidence": "high",
    "reason": "Exercise partial-success semantics with one known and one missing record.",
    "steps": [
        {
            "tool": "package_search",
            "arguments": {"package": "openssl"},
            "reason": "Retrieve a known package record."
        },
        {
            "tool": "version_compare",
            "arguments": {"package": "nonexistent"},
            "reason": "Exercise an expected missing version record."
        }
    ]
}


def run_verifier_evaluation() -> dict[str, Any]:
    injected_cases = json.loads(VERIFIER_CASES_PATH.read_text(encoding="utf-8"))
    injected_results = [_evaluate_injected_case(case) for case in injected_cases]
    legitimate_cases = [
        case
        for path in LEGITIMATE_CASE_PATHS
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]
    false_rejections = []
    for case in legitimate_cases:
        result = run_agent(case["query"], persist_trajectory=False)
        if not result["verification"]["passed"]:
            false_rejections.append({
                "query": case["query"],
                "issues": result["verification"]["issues"],
            })

    status_results = _evaluate_status_classification()
    repair_result = _evaluate_single_repair()
    invalid_citation_cases = [
        item for item in injected_results if item["expected_issue"] == "invalid_citation_reference"
    ]

    return {
        "benchmark": "Software-Agent-Verifier",
        "injected_total": len(injected_results),
        "injected_error_detection": _ratio(
            sum(1 for item in injected_results if item["detected"]),
            len(injected_results),
        ),
        "legitimate_total": len(legitimate_cases),
        "false_rejection_rate": _ratio(len(false_rejections), len(legitimate_cases)),
        "partial_success_classification": _ratio(
            sum(1 for item in status_results if item["correct"]),
            len(status_results),
        ),
        "invalid_citation_detection": _ratio(
            sum(1 for item in invalid_citation_cases if item["detected"]),
            len(invalid_citation_cases),
        ),
        "single_repair_passed": repair_result["passed"],
        "max_repair_count": repair_result["repair_count"],
        "bad_case_count": (
            sum(1 for item in injected_results if not item["detected"])
            + len(false_rejections)
            + sum(1 for item in status_results if not item["correct"])
            + (0 if repair_result["passed"] else 1)
        ),
        "injected_results": injected_results,
        "false_rejections": false_rejections,
        "status_results": status_results,
        "repair_result": repair_result,
    }


def _evaluate_injected_case(case: dict[str, Any]) -> dict[str, Any]:
    context = _build_context(case["query"], case.get("plan_kind"))
    _apply_mutation(context, case["mutation"])
    verification = DeterministicVerifier().verify(**context)
    issue_types = {issue["type"] for issue in verification.issues}
    return {
        "id": case["id"],
        "expected_issue": case["expected_issue"],
        "detected": case["expected_issue"] in issue_types,
        "passed": verification.passed,
        "issue_types": sorted(issue_types),
    }


def _build_context(query: str, plan_kind: str | None = None) -> dict[str, Any]:
    plan = copy.deepcopy(PARTIAL_PLAN) if plan_kind == "partial" else build_plan(query)
    execution = execute_plan(query, plan)
    observations = execution["observations"]
    evidence_items = _extract_evidence_items(observations)
    return {
        "plan": plan,
        "observations": observations,
        "answer": generate_final_answer(plan, observations),
        "evidence_items": evidence_items,
        "citations": citations_from_evidence(evidence_items),
        "execution_status": aggregate_execution_status(observations),
    }


def _apply_mutation(context: dict[str, Any], mutation: str) -> None:
    if mutation == "fabricated_version":
        context["answer"] = context["answer"].replace("3.0.8", "9.9.9")
    elif mutation == "wrong_dependency_direction":
        context["answer"] = "libpcap.so depends on: tcpdump."
    elif mutation == "invalid_citation":
        context["citations"][0]["evidence_id"] = "ev_missing_reference"
    elif mutation == "missing_tool_step":
        missing_tool = context["plan"]["steps"][-1]["tool"]
        context["observations"] = [
            item for item in context["observations"]
            if item["tool"] != missing_tool
        ]
        _refresh_evidence(context)
    elif mutation == "execution_status_mismatch":
        context["execution_status"] = "failed"
    elif mutation == "empty_answer":
        context["answer"] = ""
    elif mutation == "not_found_with_evidence":
        evidence = Evidence.create(
            source_type="fabricated_record",
            source_id="injected#not-found",
            title="Injected unsupported record",
            content="This record must not be exposed for a not_found result.",
            tool_name="component_mapping",
        )
        context["evidence_items"] = [evidence.to_dict()]
        context["citations"] = [Citation.from_evidence(evidence).to_dict()]
    elif mutation == "hybrid_answer_incomplete":
        context["answer"] = "Target packages: openssl 3.0.8."
    elif mutation == "missing_citation":
        context["citations"] = []
    elif mutation == "missing_arguments":
        context["plan"]["steps"][0]["arguments"] = {}
    elif mutation == "drop_observation_evidence":
        observation = context["observations"][0]["observation"]
        observation["evidence_items"] = []
        observation["normalized_observation"]["evidence"] = []
        _refresh_evidence(context)
    else:
        raise ValueError(f"Unknown verifier mutation: {mutation}")


def _refresh_evidence(context: dict[str, Any]) -> None:
    evidence_items = _extract_evidence_items(context["observations"])
    context["evidence_items"] = evidence_items
    context["citations"] = citations_from_evidence(evidence_items)


def _evaluate_status_classification() -> list[dict[str, Any]]:
    scenarios = [
        ("all_success", ["success", "success"], "success"),
        ("mixed_success_not_found", ["success", "not_found"], "partial_success"),
        ("all_not_found", ["not_found", "not_found"], "not_found"),
        ("contains_failed", ["success", "failed"], "failed"),
        ("contains_partial", ["success", "partial_success"], "partial_success"),
    ]
    results = []
    for name, statuses, expected in scenarios:
        observations = [
            {"tool": f"tool_{index}", "observation": {"status": status}}
            for index, status in enumerate(statuses)
        ]
        actual = aggregate_execution_status(observations)
        results.append({
            "scenario": name,
            "expected": expected,
            "actual": actual,
            "correct": actual == expected,
        })
    return results


def _evaluate_single_repair() -> dict[str, Any]:
    context = _build_context("query openssl version")
    correct_answer = context["answer"]
    context["answer"] = correct_answer.replace("3.0.8", "9.9.9")
    repaired_answer, verification = DeterministicVerifier().verify_and_repair(
        **context,
        answer_composer=lambda: correct_answer,
    )
    return {
        "passed": verification.passed and repaired_answer == correct_answer,
        "repair_count": verification.repair_count,
        "initial_issue_types": sorted(
            issue["type"] for issue in verification.initial_issues
        ),
        "remaining_issues": verification.issues,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


if __name__ == "__main__":
    print(json.dumps(run_verifier_evaluation(), ensure_ascii=False, indent=2))
