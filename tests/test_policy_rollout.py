from __future__ import annotations

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.feedback.models import PolicyCandidate
from app.feedback.repository import CandidateRepository
from app.policy.engine import PolicyConfigValidator, PolicyEngine
from app.policy.monitor import PolicyMonitor
from app.policy.repository import BASE_POLICY_ID, PolicyRepository
from app.policy.service import PolicyReleaseService
from evaluation.policy_eval import run_policy_evaluation


def _candidate(candidate_id="approved-candidate"):
    return PolicyCandidate(
        candidate_id=candidate_id,
        schema_version="policy-candidate-v1",
        asset_type="router_hook",
        status="approved",
        source_feedback_ids=["one", "two", "three"],
        fingerprint="wrong_tool:dependency_analysis:prerequisites",
        config={"rules": [{
            "hook_id": "prerequisites-dependency",
            "match": {"terms": ["prerequisites"], "mode": "any"},
            "action": {"intent": "dependency_analysis", "tool": "dependency_analysis"},
            "priority": 100,
        }]},
        safety_scope={
            "allowed_changes": ["router_hook_config"],
            "forbidden_changes": [
                "python_source", "datasets", "test_assertions", "permissions", "release_gates"
            ],
            "automatic_activation": False,
        },
        created_at="test",
        evaluation={"passed": True},
        review={"decision": "approve", "reviewer": "tester"},
    )


def _service(tmp_path=None, min_samples=3):
    repository = PolicyRepository(path=(tmp_path / "policy.json") if tmp_path else None)
    monitor = PolicyMonitor(min_samples=min_samples)
    engine = PolicyEngine(repository, monitor)
    candidates = CandidateRepository()
    candidates.save(_candidate())
    service = PolicyReleaseService(
        repository=repository,
        engine=engine,
        candidates=candidates,
    )
    return service, repository, engine, candidates


def test_policy_config_validation_rejects_unknown_tools_and_modes():
    validator = PolicyConfigValidator()
    invalid = {"rules": [{
        "hook_id": "bad",
        "match": {"terms": ["x"], "mode": "regex"},
        "action": {"intent": "bad", "tool": "shell"},
        "priority": 1,
    }]}

    assert "unsupported_match_mode" in validator.validate(invalid)
    assert "invalid_action_tool" in validator.validate(invalid)


def test_approved_candidate_starts_versioned_twenty_percent_rollout():
    service, repository, engine, candidates = _service()
    released = service.release_candidate(
        "approved-candidate", rollout_percentage=20, released_by="tester"
    )
    policy = released["policy"]

    assert policy["policy_id"] == "policy_v2"
    assert policy["status"] == "rollout"
    assert policy["parent_policy_id"] == BASE_POLICY_ID
    assert policy["rollout_percentage"] == 20.0
    assert repository.stable_policy_id == BASE_POLICY_ID
    assert repository.rollout_policy_id == "policy_v2"
    assert candidates.get("approved-candidate").active is True


def test_stable_hash_assignment_is_repeatable_and_near_rollout_percentage():
    service, repository, engine, _ = _service()
    service.release_candidate("approved-candidate", rollout_percentage=20, released_by="tester")

    first = engine.assign("same-session")
    assert engine.assign("same-session") == first
    rollout_count = sum(
        engine.assign(f"session-{index}").cohort == "rollout"
        for index in range(1000)
    )
    assert 150 <= rollout_count <= 250


def test_workflow_records_selected_policy_and_trace_keeps_history():
    service, repository, engine, _ = _service(min_samples=100)
    service.release_candidate("approved-candidate", rollout_percentage=20, released_by="tester")
    rollout_session = next(
        f"rollout-{index}" for index in range(1000)
        if engine.assign(f"rollout-{index}").cohort == "rollout"
    )
    traces = TraceRepository()
    result = run_agent(
        "openssl prerequisites",
        persist_trajectory=False,
        session_id=rollout_session,
        session_repository=SessionRepository(),
        trace_repository=traces,
        policy_engine=engine,
    )

    assert result["policy_version"] == "policy_v2"
    assert result["selected_tool"] == "dependency_analysis"
    assert result["policy_assignment"]["cohort"] == "rollout"
    assert traces.get(result["trace_id"])["policy_version"] == "policy_v2"


def test_monitor_automatically_rolls_back_and_deactivates_candidate():
    service, repository, engine, candidates = _service(min_samples=3)
    service.release_candidate("approved-candidate", rollout_percentage=20, released_by="tester")

    response = None
    for _ in range(3):
        service.record_monitor_sample(BASE_POLICY_ID, success=True, latency_ms=1)
        response = service.record_monitor_sample("policy_v2", success=False, latency_ms=1)

    assert response["event"]["action"] == "rollback"
    assert repository.stable_policy_id == BASE_POLICY_ID
    assert repository.rollout_policy_id is None
    assert repository.get("policy_v2").status == "rolled_back"
    assert candidates.get("approved-candidate").active is False


def test_promote_then_manual_rollback_restores_parent_without_source_edit():
    service, repository, engine, _ = _service()
    service.release_candidate("approved-candidate", rollout_percentage=20, released_by="tester")
    promoted = service.promote("policy_v2")

    assert promoted["status"] == "active"
    assert repository.stable_policy_id == "policy_v2"
    rollback = service.rollback("policy_v2", reason="manual test rollback")
    assert rollback["state"]["stable_policy_id"] == BASE_POLICY_ID
    assert repository.get("policy_v2").status == "rolled_back"


def test_policy_repository_persists_and_reloads_state(tmp_path):
    service, repository, engine, _ = _service(tmp_path=tmp_path)
    service.release_candidate("approved-candidate", rollout_percentage=20, released_by="tester")
    reloaded = PolicyRepository(path=tmp_path / "policy.json")

    assert reloaded.stable_policy_id == BASE_POLICY_ID
    assert reloaded.rollout_policy_id == "policy_v2"
    assert reloaded.get("policy_v2").config == repository.get("policy_v2").config


def test_unapproved_candidate_cannot_create_policy():
    service, repository, engine, candidates = _service()
    draft = _candidate("draft-candidate")
    draft.status = "pending_review"
    candidates.save(draft)

    try:
        service.release_candidate("draft-candidate", rollout_percentage=20, released_by="tester")
    except ValueError as exc:
        assert "approved" in str(exc)
    else:
        raise AssertionError("Unapproved candidate unexpectedly created a policy.")


def test_policy_rollout_evaluation_passes_all_gates():
    report = run_policy_evaluation()

    assert report["passed"]
    assert 0.15 <= report["observed_rollout_rate"] <= 0.25
    assert report["rollout"]["policy_version"] == "policy_v2"
    assert report["post_rollback_state"]["stable_policy_id"] == BASE_POLICY_ID
    assert report["source_hash_before"] == report["source_hash_after"]
    assert report["bad_cases"] == []
