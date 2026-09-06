"""Evaluate Step 38 trace-driven continuous Shadow evolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "evaluation" / "continuous_evolution_report.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.evolution.continuous import (
    ContinuousEvolutionRepository,
    ContinuousShadowEvolutionService,
)
from app.evolution.repository import EvolutionRepository
from app.feedback.repository import CandidateRepository, FeedbackRepository
from app.feedback.service import ControlledFeedbackLoop

HEALTHY_QUERIES = [
    "query openssl package metadata",
    "show nginx dependencies",
    "compare tcpdump version changes",
    "which package owns libssl.so",
    "find openssl manual documentation",
]
DRIFT_QUERIES = [
    "openssl prerequisites",
    "nginx prerequisites",
    "tcpdump prerequisites",
    "show ethtool dependencies",
    "compare openssl version changes",
]


def run_continuous_evolution_evaluation(*, write_report: bool = False) -> dict[str, Any]:
    traces = TraceRepository(max_records=100)
    feedback = FeedbackRepository(max_records=100)
    evolution = EvolutionRepository()
    continuous = ContinuousEvolutionRepository()
    service = ContinuousShadowEvolutionService(
        traces=traces,
        feedback=feedback,
        evolution=evolution,
        repository=continuous,
        minimum_cluster_support=2,
        default_batch_size=5,
    )
    feedback_loop = ControlledFeedbackLoop(
        traces=traces,
        feedback=feedback,
        candidates=CandidateRepository(),
        minimum_feedback=3,
    )
    sessions = SessionRepository(max_sessions=50)

    for index, query in enumerate(HEALTHY_QUERIES):
        run_agent(
            query,
            persist_trajectory=False,
            session_id=f"continuous-healthy-{index}",
            session_repository=sessions,
            trace_repository=traces,
        )
    baseline = service.scan(batch_size=5)

    drift_trace_ids = []
    for index, query in enumerate(DRIFT_QUERIES):
        result = run_agent(
            query,
            persist_trajectory=False,
            session_id=f"continuous-drift-{index}",
            session_repository=sessions,
            trace_repository=traces,
        )
        if query.endswith("prerequisites"):
            drift_trace_ids.append(result["trace_id"])
            feedback_loop.submit_feedback(
                trace_id=result["trace_id"],
                rating=-1,
                expected_tool="dependency_analysis",
                issue_type="wrong_tool",
                comment="Expected dependency semantics for prerequisites.",
            )
    degraded = service.scan(batch_size=5)
    idle = service.scan(batch_size=5)
    candidates = evolution.candidates()
    evaluations = [item.shadow_evaluation for item in candidates]
    fixed_count = sum(item.get("fixed_bad_case_count", 0) for item in evaluations)
    regression_count = sum(item.get("regressed_case_count", 0) for item in evaluations)
    thresholds = {
        "healthy_reference_initialized": baseline["status"] == "healthy"
        and baseline["drift"]["reference_available"] is False,
        "trace_batch_cursor_resumed": baseline["cursor_after"] == degraded["cursor_before"],
        "degraded_window_detected": degraded["drift"]["detected"] is True,
        "three_low_quality_actionable_traces": degraded["low_quality_count"] == 3
        and degraded["actionable_count"] == 3,
        "one_supported_candidate_generated": len(candidates) == 1,
        "all_candidates_pending_review": all(
            item.status == "pending_review" and not item.active for item in candidates
        ),
        "all_linked_failures_fixed": fixed_count == len(drift_trace_ids) == 3,
        "frozen_regressions_zero": regression_count == 0,
        "empty_follow_up_is_idempotent": idle["status"] == "idle"
        and idle["processed_trace_count"] == 0,
        "automatic_activation_blocked": degraded["automatic_activation"] is False,
        "human_review_required": degraded["human_review_required"] is True,
    }
    report = {
        "benchmark": "Software-Agent-Continuous-Shadow-Evolution",
        "schema_version": "continuous-evolution-report-v1",
        "mode": "trace_driven_continuous_shadow",
        "baseline_cycle": baseline,
        "drift_cycle": degraded,
        "idle_cycle": idle,
        "processed_trace_count": service.state()["processed_trace_count"],
        "low_quality_trace_count": degraded["low_quality_count"],
        "actionable_trace_count": degraded["actionable_count"],
        "drift_signals": degraded["drift"]["signals"],
        "candidate_count": len(candidates),
        "candidate_statuses": [item.status for item in candidates],
        "fixed_bad_case_count": fixed_count,
        "regressed_case_count": regression_count,
        "thresholds": thresholds,
        "paid_api_calls": 0,
        "passed": all(thresholds.values()),
        "bad_cases": [key for key, passed in thresholds.items() if not passed],
    }
    if write_report:
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    evaluation = run_continuous_evolution_evaluation(write_report=True)
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    raise SystemExit(0 if evaluation["passed"] else 1)
