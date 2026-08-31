"""Evaluate the Step 33 reviewed Evolution-to-Policy bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evolution.bridge import EvolutionPolicyBridgeService
from app.evolution.models import EvolutionCandidate
from app.evolution.repository import EvolutionRepository
from app.feedback.repository import CandidateRepository
from app.policy.engine import PolicyEngine
from app.policy.monitor import PolicyMonitor
from app.policy.repository import BASE_POLICY_ID, PolicyRepository
from app.policy.service import PolicyReleaseService


def run_evolution_bridge_evaluation() -> dict[str, Any]:
    evolution = EvolutionRepository()
    candidates = _reviewed_candidate_snapshots()
    for candidate in candidates:
        evolution.save_candidate(candidate)

    policies = PolicyRepository()
    engine = PolicyEngine(policies, PolicyMonitor(min_samples=1000))
    bridge = EvolutionPolicyBridgeService(evolution=evolution, policies=policies)
    release_service = PolicyReleaseService(
        repository=policies,
        engine=engine,
        candidates=CandidateRepository(),
        evolution_candidates=evolution,
    )
    releases = []
    replays = []
    rollback_states = []
    merged_keys = []
    for candidate in evolution.candidates():
        released = bridge.release(
            candidate.candidate_id,
            rollout_percentage=20,
            released_by="step33-release-owner",
        )
        replayed = bridge.release(
            candidate.candidate_id,
            rollout_percentage=20,
            released_by="step33-release-owner",
        )
        releases.append(released)
        replays.append(replayed)
        merged_keys.append(sorted(released["policy"]["config"]))
        release_service.promote(released["policy"]["policy_id"])

    last_policy_id = releases[-1]["policy"]["policy_id"]
    rollback = release_service.rollback(last_policy_id, reason="Step 33 rollback drill")
    rollback_states.append(rollback["state"])
    source_candidate = evolution.get_candidate(releases[-1]["bridge"]["candidate_id"])

    thresholds = {
        "offline_candidates_reviewed": all(
            item.status == "approved" for item in evolution.candidates()
        ),
        "three_supported_assets_released": len(releases) == 3,
        "one_policy_per_candidate": len(policies.list()) == 4,
        "immutable_bridge_per_candidate": len(evolution.bridges()) == 3,
        "all_replays_idempotent": all(item["idempotent_replay"] for item in replays),
        "candidate_and_config_digests_recorded": all(
            len(item["bridge"]["candidate_digest"]) == 64
            and len(item["bridge"]["config_digest"]) == 64
            for item in releases
        ),
        "policy_config_accumulates_reviewed_assets": set(merged_keys[-1])
        == {"aliases", "retriever", "rules"},
        "rollback_restores_parent": rollback["state"]["stable_policy_id"]
        != last_policy_id,
        "rollback_deactivates_source_candidate": bool(
            source_candidate
            and not source_candidate.active
            and source_candidate.review.get("activation_status") == "rolled_back"
        ),
        "automatic_activation_remains_blocked": all(
            item.safety_scope["automatic_activation"] is False for item in candidates
        ),
    }
    return {
        "benchmark": "Software-Agent-Reviewed-Evolution-Policy-Bridge",
        "candidate_type_count": len({item.asset_type for item in candidates}),
        "policy_versions_created": len(releases),
        "idempotency_replays": sum(item["idempotent_replay"] for item in replays),
        "bridge_record_count": len(evolution.bridges()),
        "stable_policy_before_rollback": last_policy_id,
        "stable_policy_after_rollback": rollback_states[-1]["stable_policy_id"],
        "base_policy_id": BASE_POLICY_ID,
        "thresholds": thresholds,
        "paid_api_calls": 0,
        "passed": all(thresholds.values()),
        "bad_cases": [key for key, passed in thresholds.items() if not passed],
    }


def _reviewed_candidate_snapshots() -> list[EvolutionCandidate]:
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
    return [
        EvolutionCandidate(
            candidate_id=f"evo_step33_{asset_type}",
            schema_version="evolution-candidate-v1",
            asset_type=asset_type,
            status="approved",
            source_cluster_id=f"cluster_step33_{asset_type}",
            source_failure_ids=[f"failure_step33_{asset_type}"],
            config=config,
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
                "schema_version": "shadow-eval-v1",
                "passed": True,
                "fixed_bad_case_count": 3,
                "regressed_case_count": 0,
            },
            review={
                "decision": "approve",
                "reviewer": "step33-human-reviewer",
                "reviewed_at": "2026-08-30T00:01:00+00:00",
                "activation_status": "not_activated_manual_release_required",
            },
        )
        for asset_type, config in configs.items()
    ]
if __name__ == "__main__":
    print(json.dumps(run_evolution_bridge_evaluation(), ensure_ascii=False, indent=2))
