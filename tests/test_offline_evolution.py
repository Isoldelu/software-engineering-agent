from __future__ import annotations

import pytest

from app.api.schemas import EvolutionReviewRequest
from app.api.server import app
from app.evolution.candidate import EvolutionConfigValidator
from app.evolution.models import EvolutionCandidate
from app.evolution.service import OfflineEvolutionService
from app.rag.retriever import DocumentRetriever
from evaluation.evolution_eval import run_evolution_evaluation


@pytest.fixture(scope="module")
def evaluated_cycle():
    service = OfflineEvolutionService()
    discovery = service.scan()
    candidates = service.evaluate_all()
    return service, discovery, candidates


def test_offline_miner_discovers_and_clusters_three_failure_types(evaluated_cycle):
    _, discovery, _ = evaluated_cycle

    assert discovery["failure_count"] == 9
    assert discovery["cluster_count"] == 3
    assert {item["issue_type"] for item in discovery["clusters"]} == {
        "router_miss", "entity_alias_miss", "retriever_rank_miss"
    }
    assert all(item["support"] >= 2 for item in discovery["clusters"])


def test_candidates_are_configuration_only_and_cannot_self_activate(evaluated_cycle):
    service, _, candidates = evaluated_cycle

    assert {item.asset_type for item in candidates} == {
        "router_rule", "query_alias", "retriever_weights"
    }
    for candidate in candidates:
        assert EvolutionConfigValidator().validate(candidate) == []
        assert candidate.safety_scope["automatic_activation"] is False
        assert candidate.safety_scope["requires_human_review"] is True
        with pytest.raises(PermissionError, match="cannot self-activate"):
            service.activate_candidate(candidate.candidate_id)


def test_all_shadow_candidates_fix_linked_cases_without_regression(evaluated_cycle):
    _, discovery, candidates = evaluated_cycle

    assert sum(item.shadow_evaluation["fixed_bad_case_count"] for item in candidates) == 9
    assert sum(item.shadow_evaluation["regressed_case_count"] for item in candidates) == 0
    assert all(item.status == "pending_review" for item in candidates)
    assert all(item.shadow_evaluation["passed"] for item in candidates)
    assert discovery["automatic_source_changes"] is False


def test_review_is_human_only_and_does_not_activate(evaluated_cycle):
    service, _, candidates = evaluated_cycle
    reviewed = service.review_candidate(
        candidates[0].candidate_id,
        decision="approve",
        reviewer="offline-reviewer",
        note="Shadow gates passed; release remains separate.",
    )

    assert reviewed.status == "approved"
    assert reviewed.active is False
    assert reviewed.review["activation_status"] == "not_activated_manual_release_required"


def test_invalid_evolution_candidate_scope_is_rejected():
    candidate = EvolutionCandidate(
        candidate_id="unsafe",
        schema_version="evolution-candidate-v1",
        asset_type="python_source",
        status="draft",
        source_cluster_id="cluster",
        source_failure_ids=[],
        config={"patch": "edit router.py"},
        safety_scope={"automatic_activation": True},
        created_at="now",
    )

    issues = EvolutionConfigValidator().validate(candidate)
    assert "unsupported_asset_type" in issues
    assert "automatic_activation_not_blocked" in issues
    assert "human_review_not_required" in issues


def test_hybrid_weights_are_explicit_and_backward_compatible():
    default = DocumentRetriever(mode="hybrid").retrieve("openssl manual")
    explicit = DocumentRetriever(
        mode="hybrid",
        hybrid_weights={"rrf_weight": 100.0, "reranker_weight": 1.0},
    ).retrieve("openssl manual")

    assert default == explicit


def test_evolution_api_and_schema_are_exposed():
    paths = {route.path for route in app.routes}
    review = EvolutionReviewRequest(decision="approve", reviewer="alice")

    assert review.decision == "approve"
    assert "/evolution/scan" in paths
    assert "/evolution/state" in paths
    assert "/evolution/candidates/{candidate_id}/shadow-evaluate" in paths
    assert "/evolution/candidates/{candidate_id}/review" in paths
    assert "/evaluation/evolution" in paths


def test_offline_evolution_evaluation_meets_all_gates():
    report = run_evolution_evaluation()

    assert report["passed"]
    assert report["paid_api_calls"] == 0
    assert report["fixed_bad_case_count"] == 9
    assert report["regressed_case_count"] == 0
    assert report["bad_cases"] == []
