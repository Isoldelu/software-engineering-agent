"""Evaluate the Step 25 offline controlled self-evolution cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evolution.service import OfflineEvolutionService


def run_evolution_evaluation() -> dict[str, Any]:
    service = OfflineEvolutionService()
    discovery = service.scan()
    candidates = service.evaluate_all()
    evaluations = [item.shadow_evaluation for item in candidates]
    activation_blocked = False
    try:
        service.activate_candidate(candidates[0].candidate_id)
    except PermissionError:
        activation_blocked = True

    candidate_types = sorted(item.asset_type for item in candidates)
    fixed_count = sum(item["fixed_bad_case_count"] for item in evaluations)
    regressed_count = sum(item["regressed_case_count"] for item in evaluations)
    thresholds = {
        "nine_failures_mined": discovery["failure_count"] == 9,
        "three_root_cause_clusters": discovery["cluster_count"] == 3,
        "three_candidate_types": candidate_types == [
            "query_alias", "retriever_weights", "router_rule"
        ],
        "minimum_cluster_support_enforced": all(
            cluster["support"] >= 2 for cluster in discovery["clusters"]
        ),
        "all_shadow_gates_passed": all(item["passed"] for item in evaluations),
        "all_candidates_pending_review": all(
            item.status == "pending_review" and not item.active for item in candidates
        ),
        "all_mined_failures_fixed": fixed_count == discovery["failure_count"],
        "regressed_cases_zero": regressed_count == 0,
        "automatic_source_changes_blocked": not discovery["automatic_source_changes"],
        "automatic_activation_blocked": activation_blocked,
        "human_review_required": discovery["human_review_required"],
    }
    return {
        "benchmark": "Software-Agent-Offline-Controlled-Evolution",
        "mode": discovery["mode"],
        "mined_failure_count": discovery["failure_count"],
        "cluster_count": discovery["cluster_count"],
        "candidate_count": discovery["candidate_count"],
        "candidate_types": candidate_types,
        "fixed_bad_case_count": fixed_count,
        "regressed_case_count": regressed_count,
        "candidates": [item.to_dict() for item in candidates],
        "clusters": discovery["clusters"],
        "thresholds": thresholds,
        "paid_api_calls": 0,
        "passed": all(thresholds.values()),
        "bad_cases": [key for key, passed in thresholds.items() if not passed],
    }


if __name__ == "__main__":
    print(json.dumps(run_evolution_evaluation(), ensure_ascii=False, indent=2))
