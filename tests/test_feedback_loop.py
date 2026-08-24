from __future__ import annotations

import pytest

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.api.schemas import CandidateReviewRequest, FeedbackSubmitRequest
from app.feedback.models import PolicyCandidate
from app.feedback.policy import CandidateConfigValidator
from app.feedback.repository import CandidateRepository, FeedbackRepository
from app.feedback.service import ControlledFeedbackLoop
from evaluation.feedback_loop_eval import run_feedback_loop_evaluation


QUERIES = ("openssl prerequisites", "nginx prerequisites", "tcpdump prerequisites")


def _build_loop(feedback_count=3):
    traces = TraceRepository(max_records=50)
    loop = ControlledFeedbackLoop(
        traces=traces,
        feedback=FeedbackRepository(),
        candidates=CandidateRepository(),
        minimum_feedback=3,
    )
    records = []
    for index, query in enumerate(QUERIES[:feedback_count]):
        result = run_agent(
            query,
            persist_trajectory=False,
            session_id=f"feedback-{index}",
            session_repository=SessionRepository(),
            trace_repository=traces,
        )
        records.append(loop.submit_feedback(
            trace_id=result["trace_id"],
            rating=-1,
            expected_tool="dependency_analysis",
            issue_type="wrong_tool",
        ))
    return loop, records


def test_feedback_requires_existing_trace_and_links_observation():
    loop, records = _build_loop(1)
    record = records[0]

    assert record.issue_type == "wrong_tool"
    assert record.observed["selected_tool"] == "package_search"
    assert record.observed["classification"]["trigger"] == "prerequisites"
    assert record.observed["policy_version"] == "deterministic-policy-v1"
    with pytest.raises(KeyError, match="Trace not found"):
        loop.submit_feedback(trace_id="missing", rating=-1)


def test_candidate_threshold_blocks_groups_smaller_than_three():
    loop, records = _build_loop(2)

    with pytest.raises(ValueError, match="At least 3"):
        loop.propose_candidate(records[0].fingerprint)
    assert loop.list_candidates() == []


def test_proposer_creates_configuration_only_router_hook():
    loop, records = _build_loop()
    candidate = loop.propose_candidate(records[0].fingerprint)

    assert candidate.status == "draft"
    assert candidate.asset_type == "router_hook"
    assert candidate.config["rules"][0]["match"]["terms"] == ["prerequisites"]
    assert candidate.config["rules"][0]["action"]["tool"] == "dependency_analysis"
    assert candidate.safety_scope["automatic_activation"] is False
    assert CandidateConfigValidator().validate(candidate) == []
    assert all(item.status == "candidate_created" for item in loop.feedback.list())


def test_candidate_replay_improves_linked_cases_without_regression():
    loop, records = _build_loop()
    candidate = loop.propose_candidate(records[0].fingerprint)
    candidate = loop.evaluate_candidate(candidate.candidate_id)
    evaluation = candidate.evaluation

    assert candidate.status == "pending_review"
    assert candidate.active is False
    assert evaluation["baseline_score"] == 0.0
    assert evaluation["candidate_score"] == 1.0
    assert evaluation["fixed_bad_case_count"] == 3
    assert evaluation["regression_case_count"] == 193
    assert evaluation["regressed_case_count"] == 0
    assert all(evaluation["gates"].values())


def test_human_review_does_not_activate_candidate_and_activation_is_blocked():
    loop, records = _build_loop()
    candidate = loop.evaluate_candidate(loop.propose_candidate(records[0].fingerprint).candidate_id)
    reviewed = loop.review_candidate(
        candidate.candidate_id,
        decision="approve",
        reviewer="human-reviewer",
        note="Ready for Step 23 rollout design.",
    )

    assert reviewed.status == "approved"
    assert reviewed.active is False
    assert reviewed.review["activation_status"] == "not_activated_step23_required"
    with pytest.raises(PermissionError, match="Step 23"):
        loop.activate_candidate(reviewed.candidate_id)


def test_review_rejects_invalid_state_and_reviewer():
    loop, records = _build_loop()
    draft = loop.propose_candidate(records[0].fingerprint)

    with pytest.raises(ValueError, match="pending_review"):
        loop.review_candidate(draft.candidate_id, decision="approve", reviewer="reviewer")


def test_config_validator_rejects_source_and_gate_mutation_scope():
    candidate = PolicyCandidate(
        candidate_id="unsafe",
        schema_version="policy-candidate-v1",
        asset_type="python_source",
        status="draft",
        source_feedback_ids=[],
        fingerprint="unsafe",
        config={"source_patch": "modify router.py"},
        safety_scope={"forbidden_changes": []},
        created_at="now",
    )

    issues = CandidateConfigValidator().validate(candidate)
    assert "forbidden_asset_type" in issues
    assert "invalid_config_keys" in issues
    assert "incomplete_safety_scope" in issues


def test_feedback_api_schemas_validate_controlled_inputs():
    feedback = FeedbackSubmitRequest(
        trace_id="trace",
        rating=-1,
        expected_tool="dependency_analysis",
    )
    review = CandidateReviewRequest(decision="approve", reviewer="alice")

    assert feedback.rating == -1
    assert review.decision == "approve"


def test_feedback_loop_evaluation_meets_all_gates():
    report = run_feedback_loop_evaluation()

    assert report["passed"]
    assert report["feedback_trace_linkage"] == 1.0
    assert report["classification_accuracy"] == 1.0
    assert report["minimum_feedback_enforced"] is True
    assert report["fixed_bad_case_count"] == 3
    assert report["regressed_case_count"] == 0
    assert report["candidate_status"] == "pending_review"
    assert report["candidate_active"] is False
    assert report["bad_cases"] == []
