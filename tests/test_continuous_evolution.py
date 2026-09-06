from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.trace import TraceRepository
from app.api.schemas import ContinuousEvolutionScanRequest
from app.api.server import app
from app.evolution.continuous import (
    ContinuousEvolutionRepository,
    TraceDriftDetector,
    TraceQualityScorer,
)
from app.feedback.models import FeedbackRecord
from app.security.api_key import required_role
from app.storage.database import ControlPlaneStore
from evaluation.continuous_evolution_eval import run_continuous_evolution_evaluation


def _trace(trace_id: str, *, status: str = "success") -> dict:
    return {
        "trace_id": trace_id,
        "session_id": f"session-{trace_id}",
        "input": {"original_query": "query", "resolved_query": "query"},
        "plan": {"tool": "package_search", "intent": "package_search"},
        "steps": [{"tool": "package_search", "input": "query", "status": status}],
        "output": {
            "execution_status": status,
            "evidence_ids": ["ev_1"] if status == "success" else [],
            "verification": {"passed": status == "success"},
        },
        "metrics": {"total_latency_ms": 5.0, "tool_call_count": 1},
    }


def _feedback(trace_id: str) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=f"fb-{trace_id}",
        trace_id=trace_id,
        rating=-1,
        issue_type="wrong_tool",
        expected_tool="dependency_analysis",
        comment="wrong route",
        status="open",
        fingerprint="wrong_tool:dependency_analysis:prerequisites",
        observed={"classification": {"trigger": "prerequisites"}},
        created_at="2026-09-06T00:00:00+00:00",
    )


def test_quality_scorer_requires_explicit_feedback_for_actionable_change():
    scorer = TraceQualityScorer()
    failed = scorer.assess(
        _trace("tr-failed", status="failed"),
        [],
        batch_id="batch-1",
        assessed_at="now",
    )
    routed = scorer.assess(
        _trace("tr-routed"),
        [_feedback("tr-routed")],
        batch_id="batch-1",
        assessed_at="now",
    )

    assert failed.low_quality is True
    assert failed.actionable is False
    assert routed.low_quality is True
    assert routed.actionable is True
    assert routed.expected_tool == "dependency_analysis"
    assert "negative_feedback" in routed.signals


def test_drift_detector_uses_multiple_observable_signals():
    detector = TraceDriftDetector()
    reference = {
        "mean_quality_score": 1.0,
        "low_quality_rate": 0.0,
        "failure_rate": 0.0,
        "p95_latency_ms": 10.0,
        "tool_distribution": {"package_search": 0.5, "dependency_analysis": 0.5},
    }
    current = {
        "mean_quality_score": 0.5,
        "low_quality_rate": 0.6,
        "failure_rate": 0.2,
        "p95_latency_ms": 30.0,
        "tool_distribution": {"package_search": 1.0},
    }

    drift = detector.detect(current, reference)

    assert drift["detected"] is True
    assert {
        "quality_score_drop",
        "low_quality_rate_increase",
        "failure_rate_increase",
        "tool_distribution_shift",
        "p95_latency_increase",
    } <= set(drift["signals"])


def test_unhealthy_first_window_is_not_accepted_as_reference():
    detector = TraceDriftDetector()
    unhealthy = {
        "mean_quality_score": 0.6,
        "low_quality_rate": 0.5,
        "failure_rate": 0.2,
        "p95_latency_ms": 10.0,
        "tool_distribution": {"package_search": 1.0},
    }

    drift = detector.detect(unhealthy, None)

    assert drift["detected"] is True
    assert drift["signals"] == ["absolute_quality_threshold_breached"]


def test_trace_repository_lists_in_stable_ingestion_order():
    traces = TraceRepository(max_records=3)
    traces.save(_trace("tr-1"))
    traces.save(_trace("tr-2"))

    listed = traces.list()
    listed[0]["trace_id"] = "mutated"

    assert [item["trace_id"] for item in traces.list()] == ["tr-1", "tr-2"]


def test_continuous_state_cursor_survives_repository_restart(tmp_path: Path):
    url = "sqlite:///" + (tmp_path / "continuous.db").as_posix()
    writer_store = ControlPlaneStore(url)
    reader_store = ControlPlaneStore(url)
    state = {
        "schema_version": "continuous-evolution-state-v1",
        "last_trace_id": "tr-last",
        "processed_trace_count": 12,
        "baseline_profile": {"mean_quality_score": 1.0},
        "last_cycle_id": "cycle-1",
        "updated_at": "now",
        "automatic_activation": False,
        "human_review_required": True,
    }
    try:
        ContinuousEvolutionRepository(store=writer_store).save_state(state)
        restored = ContinuousEvolutionRepository(store=reader_store).state()
    finally:
        writer_store.close()
        reader_store.close()

    assert restored == state


@pytest.fixture(scope="module")
def continuous_report():
    return run_continuous_evolution_evaluation()


def test_two_window_continuous_shadow_cycle_meets_all_gates(continuous_report):
    assert continuous_report["passed"] is True
    assert continuous_report["processed_trace_count"] == 10
    assert continuous_report["low_quality_trace_count"] == 3
    assert continuous_report["actionable_trace_count"] == 3
    assert continuous_report["fixed_bad_case_count"] == 3
    assert continuous_report["regressed_case_count"] == 0
    assert continuous_report["bad_cases"] == []


def test_candidate_stops_at_human_review_boundary(continuous_report):
    assert continuous_report["candidate_count"] == 1
    assert continuous_report["candidate_statuses"] == ["pending_review"]
    assert continuous_report["drift_cycle"]["automatic_activation"] is False
    assert continuous_report["drift_cycle"]["human_review_required"] is True
    assert continuous_report["paid_api_calls"] == 0


def test_continuous_evolution_api_and_roles_are_exposed():
    paths = {route.path for route in app.routes}
    request = ContinuousEvolutionScanRequest(batch_size=25)

    assert request.batch_size == 25
    assert "/evolution/continuous/scan" in paths
    assert "/evolution/continuous/state" in paths
    assert "/evaluation/evolution-continuous" in paths
    assert required_role("POST", "/evolution/continuous/scan") == "operator"
    assert required_role("GET", "/evolution/continuous/state") == "reader"


def test_continuous_scan_schema_rejects_unbounded_batches():
    with pytest.raises(ValueError):
        ContinuousEvolutionScanRequest(batch_size=1001)
