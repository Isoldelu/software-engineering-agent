"""Evaluate the Step 22 controlled Feedback and bad-case optimization loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_CASES_PATH = PROJECT_ROOT / "evaluation" / "feedback_cases.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.feedback.repository import CandidateRepository, FeedbackRepository
from app.feedback.service import ControlledFeedbackLoop


def run_feedback_loop_evaluation(
    cases_path: Path = FEEDBACK_CASES_PATH,
) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    traces = TraceRepository(max_records=50)
    sessions = SessionRepository(max_sessions=20)
    feedback_repository = FeedbackRepository()
    candidate_repository = CandidateRepository()
    loop = ControlledFeedbackLoop(
        traces=traces,
        feedback=feedback_repository,
        candidates=candidate_repository,
        minimum_feedback=3,
    )

    feedback_records = []
    baseline_cases = []
    threshold_blocked = False
    for index, case in enumerate(cases, start=1):
        result = run_agent(
            case["query"],
            persist_trajectory=False,
            session_id=f"feedback-eval-{index}",
            session_repository=sessions,
            trace_repository=traces,
        )
        baseline_cases.append({
            "query": case["query"],
            "trace_id": result["trace_id"],
            "selected_tool": result["selected_tool"],
            "expected_tool": case["expected_tool"],
            "wrong_tool": result["selected_tool"] != case["expected_tool"],
        })
        feedback_records.append(loop.submit_feedback(
            trace_id=result["trace_id"],
            rating=-1,
            expected_tool=case["expected_tool"],
            issue_type="wrong_tool",
            comment="Expected dependency analysis for prerequisite intent.",
        ))
        if index == 2:
            try:
                loop.propose_candidate(feedback_records[0].fingerprint)
            except ValueError:
                threshold_blocked = True

    candidate = loop.propose_candidate(feedback_records[0].fingerprint)
    candidate = loop.evaluate_candidate(candidate.candidate_id)
    evaluation = candidate.evaluation
    classification_accuracy = sum(
        record.issue_type == "wrong_tool" for record in feedback_records
    ) / len(feedback_records)
    trace_linkage = sum(
        traces.get(record.trace_id) is not None for record in feedback_records
    ) / len(feedback_records)
    pending_without_activation = candidate.status == "pending_review" and not candidate.active
    thresholds = {
        "feedback_trace_linkage": trace_linkage == 1.0,
        "classification_accuracy": classification_accuracy == 1.0,
        "minimum_feedback_enforced": threshold_blocked,
        "candidate_score_improved": evaluation["candidate_score"] > evaluation["baseline_score"],
        "fixed_at_least_two": evaluation["fixed_bad_case_count"] >= 2,
        "regressed_cases_zero": evaluation["regressed_case_count"] == 0,
        "core_metrics_not_decreased": evaluation["gates"]["core_metrics_not_decreased"],
        "added_latency_within_15_percent": evaluation["gates"]["added_latency_within_15_percent"],
        "pending_review_not_active": pending_without_activation,
    }
    return {
        "benchmark": "Software-Agent-Controlled-Feedback-Loop",
        "feedback_count": len(feedback_records),
        "feedback_trace_linkage": trace_linkage,
        "classification_accuracy": classification_accuracy,
        "minimum_feedback_enforced": threshold_blocked,
        "candidate_id": candidate.candidate_id,
        "candidate_status": candidate.status,
        "candidate_active": candidate.active,
        "candidate_asset_type": candidate.asset_type,
        "candidate_config": candidate.config,
        "baseline_score": evaluation["baseline_score"],
        "candidate_score": evaluation["candidate_score"],
        "fixed_bad_case_count": evaluation["fixed_bad_case_count"],
        "regression_case_count": evaluation["regression_case_count"],
        "regressed_case_count": evaluation["regressed_case_count"],
        "baseline_metrics": evaluation["baseline_metrics"],
        "candidate_metrics": evaluation["candidate_metrics"],
        "added_latency_ratio": evaluation["added_latency_ratio"],
        "thresholds": thresholds,
        "passed": all(thresholds.values()),
        "baseline_cases": baseline_cases,
        "linked_results": evaluation["linked_results"],
        "bad_cases": [] if all(thresholds.values()) else [
            key for key, passed in thresholds.items() if not passed
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_feedback_loop_evaluation(), ensure_ascii=False, indent=2))
