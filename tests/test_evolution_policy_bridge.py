from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.api.schemas import EvolutionPolicyReleaseRequest
from app.api.server import app
from app.evolution.bridge import EvolutionPolicyBridgeService, EvolutionPolicyTranslator
from app.evolution.models import EvolutionCandidate
from app.evolution.repository import EvolutionRepository
from app.feedback.repository import CandidateRepository
from app.policy.engine import PolicyConfigValidator, PolicyEngine
from app.policy.monitor import PolicyMonitor
from app.policy.repository import BASE_POLICY_ID, PolicyRepository
from app.policy.service import PolicyReleaseService
from app.security.api_key import required_role
from app.storage.database import ControlPlaneStore
from evaluation.evolution_bridge_eval import run_evolution_bridge_evaluation


def _candidate(asset_type: str, *, status: str = "approved") -> EvolutionCandidate:
    configs = {
        "router_rule": {
            "rules": [{
                "hook_id": "offline_prerequisites_dependency",
                "match": {"terms": ["prerequisites"], "mode": "any"},
                "action": {
                    "intent": "dependency_analysis",
                    "tool": "dependency_analysis",
                },
                "priority": 90,
            }]
        },
        "query_alias": {"aliases": {"tls toolkit": "openssl"}},
        "retriever_weights": {
            "mode": "hybrid",
            "rrf_weight": 100.0,
            "reranker_weight": 1.0,
        },
    }
    return EvolutionCandidate(
        candidate_id=f"evo_{asset_type}",
        schema_version="evolution-candidate-v1",
        asset_type=asset_type,
        status=status,
        source_cluster_id=f"cluster_{asset_type}",
        source_failure_ids=[f"failure_{asset_type}"],
        config=configs[asset_type],
        safety_scope={
            "allowed_changes": [asset_type],
            "forbidden_changes": [
                "python_source",
                "datasets",
                "test_assertions",
                "permissions",
                "release_gates",
            ],
            "automatic_activation": False,
            "requires_human_review": True,
        },
        created_at="2026-08-30T00:00:00+00:00",
        shadow_evaluation={
            "passed": True,
            "fixed_bad_case_count": 3,
            "regressed_case_count": 0,
        },
        review={
            "decision": "approve",
            "reviewer": "human-reviewer",
            "reviewed_at": "2026-08-30T00:01:00+00:00",
            "activation_status": "not_activated_manual_release_required",
        },
    )


def _bridge(asset_type: str = "router_rule", *, status: str = "approved"):
    evolution = EvolutionRepository()
    evolution.save_candidate(_candidate(asset_type, status=status))
    policies = PolicyRepository()
    service = EvolutionPolicyBridgeService(evolution=evolution, policies=policies)
    return service, evolution, policies


def _rollout_session(engine: PolicyEngine) -> str:
    return next(
        f"step33-{index}"
        for index in range(1000)
        if engine.assign(f"step33-{index}").cohort == "rollout"
    )


def test_unapproved_or_unverified_candidate_cannot_cross_bridge():
    service, evolution, policies = _bridge(status="pending_review")

    with pytest.raises(ValueError, match="approved"):
        service.release(
            "evo_router_rule", rollout_percentage=20, released_by="release-owner"
        )
    assert policies.list()[-1].policy_id == BASE_POLICY_ID
    assert evolution.bridges() == []


def test_translator_maps_all_supported_assets_to_valid_policy_config():
    translator = EvolutionPolicyTranslator()
    validator = PolicyConfigValidator()

    for asset_type in ("router_rule", "query_alias", "retriever_weights"):
        patch = translator.translate(_candidate(asset_type))
        config = translator.merge({"rules": []}, patch)
        assert validator.validate(config) == []


def test_reviewed_candidate_creates_traceable_rollout_and_idempotent_replay():
    service, evolution, policies = _bridge()
    first = service.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )
    second = service.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )

    assert first["created"] is True
    assert second["idempotent_replay"] is True
    assert first["policy"]["policy_id"] == second["policy"]["policy_id"] == "policy_v2"
    assert len(policies.list()) == 2
    assert len(evolution.bridges()) == 1
    assert first["policy"]["metadata"]["evolution_candidate_id"] == "evo_router_rule"
    assert evolution.get_candidate("evo_router_rule").active is True


def test_idempotent_replay_rejects_rollout_parameter_drift():
    service, _, _ = _bridge()
    service.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )

    with pytest.raises(ValueError, match="different rollout percentage"):
        service.release(
            "evo_router_rule", rollout_percentage=30, released_by="release-owner"
        )


def test_router_and_alias_policies_change_runtime_only_for_rollout_cohort():
    router_bridge, _, router_policies = _bridge("router_rule")
    router_bridge.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )
    router_engine = PolicyEngine(router_policies, PolicyMonitor(min_samples=1000))
    router_result = run_agent(
        "openssl prerequisites",
        persist_trajectory=False,
        session_id=_rollout_session(router_engine),
        session_repository=SessionRepository(),
        trace_repository=TraceRepository(),
        policy_engine=router_engine,
    )

    alias_bridge, _, alias_policies = _bridge("query_alias")
    alias_bridge.release(
        "evo_query_alias", rollout_percentage=20, released_by="release-owner"
    )
    alias_engine = PolicyEngine(alias_policies, PolicyMonitor(min_samples=1000))
    alias_result = run_agent(
        "query tls toolkit package info",
        persist_trajectory=False,
        session_id=_rollout_session(alias_engine),
        session_repository=SessionRepository(),
        trace_repository=TraceRepository(),
        policy_engine=alias_engine,
    )

    assert router_result["selected_tool"] == "dependency_analysis"
    assert router_result["planner_source"] == "policy_engine"
    assert alias_result["policy_transform"]["changed"] is True
    assert "openssl" in alias_result["resolved_query"]
    assert alias_result["success"] is True


def test_retriever_policy_is_passed_to_rag_tool():
    service, _, policies = _bridge("retriever_weights")
    service.release(
        "evo_retriever_weights", rollout_percentage=20, released_by="release-owner"
    )
    engine = PolicyEngine(policies, PolicyMonitor(min_samples=1000))
    result = run_agent(
        "software manual describes tcpdump as what",
        persist_trajectory=False,
        session_id=_rollout_session(engine),
        session_repository=SessionRepository(),
        trace_repository=TraceRepository(),
        policy_engine=engine,
    )

    observation = next(
        item["observation"]
        for item in result["trajectory"]
        if item.get("stage") == "tool_execution"
    )
    assert result["selected_tool"] == "rag_retrieval"
    assert observation["retriever_mode"] == "hybrid"


def test_manual_rollback_deactivates_evolution_source_candidate():
    bridge, evolution, policies = _bridge()
    released = bridge.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )
    engine = PolicyEngine(policies, PolicyMonitor(min_samples=1000))
    release_service = PolicyReleaseService(
        repository=policies,
        engine=engine,
        candidates=CandidateRepository(),
        evolution_candidates=evolution,
    )
    release_service.rollback(released["policy"]["policy_id"], reason="gate regression")

    candidate = evolution.get_candidate("evo_router_rule")
    assert candidate.active is False
    assert candidate.review["activation_status"] == "rolled_back"


def test_monitor_rollback_deactivates_evolution_source_candidate():
    bridge, evolution, policies = _bridge()
    released = bridge.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )
    engine = PolicyEngine(policies, PolicyMonitor(min_samples=3))
    release_service = PolicyReleaseService(
        repository=policies,
        engine=engine,
        candidates=CandidateRepository(),
        evolution_candidates=evolution,
    )

    response = None
    for _ in range(3):
        release_service.record_monitor_sample(
            BASE_POLICY_ID, success=True, latency_ms=1
        )
        response = release_service.record_monitor_sample(
            released["policy"]["policy_id"], success=False, latency_ms=1
        )

    candidate = evolution.get_candidate("evo_router_rule")
    assert response and response["event"]["action"] == "rollback"
    assert candidate.active is False
    assert candidate.review["activation_status"] == "automatic_rollback"


def test_concurrent_replay_creates_one_policy_and_one_bridge():
    service, evolution, policies = _bridge()

    def release():
        return service.release(
            "evo_router_rule", rollout_percentage=20, released_by="release-owner"
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: release(), range(4)))

    assert sum(item["created"] for item in results) == 1
    assert len(policies.list()) == 2
    assert len(evolution.bridges()) == 1


def test_bridge_replay_is_persistent_across_repository_instances(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "step33.db").as_posix()
    writer_store = ControlPlaneStore(database_url)
    writer_evolution = EvolutionRepository(store=writer_store)
    writer_evolution.save_candidate(_candidate("router_rule"))
    writer_policies = PolicyRepository(store=writer_store)
    writer_bridge = EvolutionPolicyBridgeService(
        evolution=writer_evolution,
        policies=writer_policies,
    )
    first = writer_bridge.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )

    reader_store = ControlPlaneStore(database_url)
    reader_bridge = EvolutionPolicyBridgeService(
        evolution=EvolutionRepository(store=reader_store),
        policies=PolicyRepository(store=reader_store),
    )
    replay = reader_bridge.release(
        "evo_router_rule", rollout_percentage=20, released_by="release-owner"
    )

    assert replay["idempotent_replay"] is True
    assert replay["policy"]["policy_id"] == first["policy"]["policy_id"]
    assert len(reader_bridge.list()) == 1
    assert len(reader_bridge.policies.list()) == 2
    writer_store.close()
    reader_store.close()


def test_bridge_api_contract_and_admin_role_are_exposed():
    paths = {route.path for route in app.routes}
    request = EvolutionPolicyReleaseRequest(released_by="release-owner")

    assert request.rollout_percentage == 20.0
    assert "/evolution/bridges" in paths
    assert "/policies/from-evolution/{candidate_id}" in paths
    assert required_role("POST", "/policies/from-evolution/evo_x") == "admin"


def test_step33_evaluation_meets_all_release_gates():
    report = run_evolution_bridge_evaluation()

    assert report["passed"]
    assert report["candidate_type_count"] == 3
    assert report["policy_versions_created"] == 3
    assert report["idempotency_replays"] == 3
    assert report["paid_api_calls"] == 0
    assert report["bad_cases"] == []
