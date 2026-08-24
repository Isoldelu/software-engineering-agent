"""Configuration-only policy hooks and isolated regression evaluation."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

from app.agent.context import SessionRepository
from app.agent.llm_router import VALID_TOOLS
from app.agent.router import extract_component, extract_package, extract_release
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.feedback.models import ALLOWED_ASSET_TYPES, FeedbackRecord, PolicyCandidate


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_PATHS = [
    PROJECT_ROOT / "evaluation" / "test_cases.json",
    PROJECT_ROOT / "evaluation" / "challenge_cases.json",
    PROJECT_ROOT / "evaluation" / "robustness_cases.json",
    PROJECT_ROOT / "evaluation" / "large_benchmark.json",
]
MAX_ADDED_LATENCY_RATIO = 0.15
LATENCY_NOISE_FLOOR_MS = 0.5

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def latency_within_budget(
    baseline_ms: float,
    candidate_ms: float,
    *,
    max_ratio: float = MAX_ADDED_LATENCY_RATIO,
    noise_floor_ms: float = LATENCY_NOISE_FLOOR_MS,
) -> bool:
    """Apply a relative latency gate without rejecting sub-millisecond CI noise."""
    added_ms = max(0.0, candidate_ms - baseline_ms)
    if added_ms <= noise_floor_ms:
        return True
    return bool(baseline_ms and added_ms / baseline_ms <= max_ratio)


class CandidateConfigValidator:
    """Reject candidates outside the explicitly permitted configuration scope."""

    def validate(self, candidate: PolicyCandidate) -> list[str]:
        issues = []
        if candidate.asset_type not in ALLOWED_ASSET_TYPES:
            issues.append("forbidden_asset_type")
        if candidate.asset_type != "router_hook":
            issues.append("unsupported_step22_asset_type")
        if set(candidate.config) != {"rules"}:
            issues.append("invalid_config_keys")
        rules = candidate.config.get("rules", [])
        if not isinstance(rules, list) or not rules:
            issues.append("missing_rules")
        for rule in rules if isinstance(rules, list) else []:
            if set(rule) != {"hook_id", "match", "action", "priority"}:
                issues.append("invalid_rule_keys")
                continue
            terms = rule.get("match", {}).get("terms", [])
            tool = rule.get("action", {}).get("tool")
            if not terms or not all(isinstance(term, str) and term for term in terms):
                issues.append("invalid_match_terms")
            if tool not in VALID_TOOLS:
                issues.append("invalid_action_tool")
        forbidden = candidate.safety_scope.get("forbidden_changes", [])
        required_forbidden = {"python_source", "datasets", "test_assertions", "permissions", "release_gates"}
        if not required_forbidden <= set(forbidden):
            issues.append("incomplete_safety_scope")
        return sorted(set(issues))


class CandidatePolicyRunner:
    def __init__(self, candidate: PolicyCandidate) -> None:
        self.candidate = candidate

    def run(self, query: str) -> dict[str, Any]:
        llm_plan = self._matching_plan(query)
        return run_agent(
            query,
            persist_trajectory=False,
            llm_plan_output=json.dumps(llm_plan) if llm_plan else None,
            session_repository=SessionRepository(max_sessions=5),
            trace_repository=TraceRepository(max_records=10),
        )

    def _matching_plan(self, query: str) -> dict[str, Any] | None:
        lowered = query.lower()
        for rule in sorted(
            self.candidate.config.get("rules", []),
            key=lambda item: item.get("priority", 0),
            reverse=True,
        ):
            terms = [term.lower() for term in rule["match"]["terms"]]
            if not any(term in lowered for term in terms):
                continue
            action = rule["action"]
            tool = action["tool"]
            arguments = {
                "package": extract_package(lowered),
                "release": extract_release(lowered),
                "component": extract_component(lowered),
                "query": query,
            }
            return {
                "intent": action["intent"],
                "tool": tool,
                "arguments": arguments,
                "confidence": "high",
                "reason": f"Matched approved-scope candidate hook {rule['hook_id']}.",
                "steps": [{
                    "tool": tool,
                    "arguments": arguments,
                    "reason": f"Candidate router hook selected {tool}.",
                }],
            }
        return None


class CandidateEvaluator:
    """Run linked bad cases and the frozen 193-case regression suite in isolation."""

    def evaluate(
        self,
        candidate: PolicyCandidate,
        feedback: list[FeedbackRecord],
    ) -> dict[str, Any]:
        config_issues = CandidateConfigValidator().validate(candidate)
        if config_issues:
            return self._rejected(candidate, config_issues)

        runner = CandidatePolicyRunner(candidate)
        linked_results = []
        for record in feedback:
            query = record.observed["resolved_query"]
            candidate_result = runner.run(query)
            expected_tool = record.expected_tool
            baseline_correct = record.observed["selected_tool"] == expected_tool
            candidate_correct = candidate_result["selected_tool"] == expected_tool
            linked_results.append({
                "feedback_id": record.feedback_id,
                "query": query,
                "expected_tool": expected_tool,
                "baseline_tool": record.observed["selected_tool"],
                "candidate_tool": candidate_result["selected_tool"],
                "baseline_correct": baseline_correct,
                "candidate_correct": candidate_correct,
                "fixed": not baseline_correct and candidate_correct,
            })

        cases = [
            case
            for path in CASE_PATHS
            for case in json.loads(path.read_text(encoding="utf-8"))
        ]
        baseline_results = []
        candidate_results = []
        for case in cases:
            baseline_results.append(_evaluate_case_result(case, _isolated_run(case["query"])))
            candidate_results.append(_evaluate_case_result(case, runner.run(case["query"])))

        baseline_metrics = _metrics(baseline_results)
        candidate_metrics = _metrics(candidate_results)
        regressed_cases = [
            {
                "query": case["query"],
                "baseline": baseline,
                "candidate": current,
            }
            for case, baseline, current in zip(cases, baseline_results, candidate_results)
            if baseline["passed"] and not current["passed"]
        ]
        baseline_score = _ratio(sum(item["baseline_correct"] for item in linked_results), len(linked_results))
        candidate_score = _ratio(sum(item["candidate_correct"] for item in linked_results), len(linked_results))
        fixed_count = sum(item["fixed"] for item in linked_results)
        baseline_latency = statistics.median(item["latency_ms"] for item in baseline_results)
        candidate_latency = statistics.median(item["latency_ms"] for item in candidate_results)
        added_latency_ms = max(0.0, candidate_latency - baseline_latency)
        added_latency_ratio = (
            added_latency_ms / baseline_latency
            if baseline_latency else 0.0
        )
        core_not_decreased = all(
            candidate_metrics[key] >= baseline_metrics[key]
            for key in ("tool_accuracy", "task_success", "grounding", "answer_accuracy")
        )
        gates = {
            "configuration_scope_valid": True,
            "candidate_score_improved": candidate_score > baseline_score,
            "fixed_at_least_two": fixed_count >= 2,
            "regressed_cases_zero": not regressed_cases,
            "core_metrics_not_decreased": core_not_decreased,
            "added_latency_within_15_percent": latency_within_budget(
                baseline_latency,
                candidate_latency,
            ),
        }
        return {
            "evaluation_schema_version": "candidate-eval-v1",
            "candidate_id": candidate.candidate_id,
            "linked_feedback_count": len(linked_results),
            "linked_results": linked_results,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "fixed_bad_case_count": fixed_count,
            "regression_case_count": len(cases),
            "regressed_case_count": len(regressed_cases),
            "regressed_cases": regressed_cases,
            "baseline_metrics": baseline_metrics,
            "candidate_metrics": candidate_metrics,
            "baseline_latency_ms": baseline_latency,
            "candidate_latency_ms": candidate_latency,
            "added_latency_ms": added_latency_ms,
            "added_latency_ratio": added_latency_ratio,
            "latency_statistic": "median",
            "latency_noise_floor_ms": LATENCY_NOISE_FLOOR_MS,
            "latency_gate_limit_ratio": MAX_ADDED_LATENCY_RATIO,
            "gates": gates,
            "passed": all(gates.values()),
            "next_status": "pending_review" if all(gates.values()) else "rejected",
        }

    @staticmethod
    def _rejected(candidate: PolicyCandidate, issues: list[str]) -> dict[str, Any]:
        return {
            "evaluation_schema_version": "candidate-eval-v1",
            "candidate_id": candidate.candidate_id,
            "config_issues": issues,
            "gates": {"configuration_scope_valid": False},
            "passed": False,
            "next_status": "rejected",
        }


def _isolated_run(query: str) -> dict[str, Any]:
    return run_agent(
        query,
        persist_trajectory=False,
        session_repository=SessionRepository(max_sessions=5),
        trace_repository=TraceRepository(max_records=10),
    )


def _evaluate_case_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected_status = case.get("expected_status", "success")
    if "expected_tools" in case:
        tool_correct = result.get("used_tools", []) == case["expected_tools"]
    else:
        tool_correct = result["selected_tool"] == case["expected_tool"]
    statuses = [
        item.get("observation", {}).get("status")
        for item in result.get("trajectory", [])
        if item.get("stage") == "tool_execution"
    ]
    if expected_status == "not_found":
        task_success = "not_found" in statuses
    else:
        task_success = result.get("success", False)
    expected = case.get("expected_answer_contains", [])
    answer_correct = all(fragment in result["answer"] for fragment in expected)
    evidence_text = json.dumps(result.get("trajectory", []), ensure_ascii=False)
    grounded = expected_status == "not_found" or (
        bool(result.get("evidence")) and all(fragment in evidence_text for fragment in expected)
    )
    passed = tool_correct and task_success and answer_correct and grounded
    return {
        "tool_correct": tool_correct,
        "task_success": task_success,
        "grounded": grounded,
        "answer_correct": answer_correct,
        "passed": passed,
        "latency_ms": result["trace"]["metrics"]["total_latency_ms"],
    }


def _metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "tool_accuracy": _ratio(sum(item["tool_correct"] for item in results), len(results)),
        "task_success": _ratio(sum(item["task_success"] for item in results), len(results)),
        "grounding": _ratio(sum(item["grounded"] for item in results), len(results)),
        "answer_accuracy": _ratio(sum(item["answer_correct"] for item in results), len(results)),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
