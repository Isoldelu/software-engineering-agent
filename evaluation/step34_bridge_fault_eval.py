"""Step 34 database-level Bridge concurrency and fault-injection evaluation."""

from __future__ import annotations

import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evolution.bridge import EvolutionPolicyBridgeService
from app.evolution.models import EvolutionCandidate, EvolutionPolicyBridge
from app.evolution.repository import EvolutionRepository
from app.feedback.repository import CandidateRepository
from app.policy.engine import PolicyEngine
from app.policy.monitor import PolicyMonitor
from app.policy.repository import PolicyRepository
from app.policy.service import PolicyReleaseService
from app.storage.database import ControlPlaneStore


class InjectedBridgeWriteFailure(RuntimeError):
    """Failure injected after Policy creation but before Bridge persistence."""


class FailOnceEvolutionRepository(EvolutionRepository):
    def __init__(self, *, store: ControlPlaneStore) -> None:
        super().__init__(store=store)
        self.fail_next_bridge_write = True

    def save_bridge_once(
        self,
        item: EvolutionPolicyBridge,
    ) -> tuple[EvolutionPolicyBridge, bool]:
        if self.fail_next_bridge_write:
            self.fail_next_bridge_write = False
            raise InjectedBridgeWriteFailure("injected bridge persistence failure")
        return super().save_bridge_once(item)


def reviewed_candidate(candidate_id: str) -> EvolutionCandidate:
    alias = f"alias-{candidate_id[-8:]}"
    return EvolutionCandidate(
        candidate_id=candidate_id,
        schema_version="evolution-candidate-v1",
        asset_type="query_alias",
        status="approved",
        source_cluster_id=f"cluster_{candidate_id}",
        source_failure_ids=[f"failure_{candidate_id}"],
        config={"aliases": {alias: "openssl"}},
        safety_scope={
            "allowed_changes": ["query_alias"],
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
        created_at="2026-08-31T00:00:00+00:00",
        shadow_evaluation={
            "schema_version": "shadow-eval-v1",
            "passed": True,
            "fixed_bad_case_count": 3,
            "regressed_case_count": 0,
        },
        review={
            "decision": "approve",
            "reviewer": "step34-human-reviewer",
            "reviewed_at": "2026-08-31T00:01:00+00:00",
            "activation_status": "not_activated_manual_release_required",
        },
    )


def run_bridge_fault_evaluation(
    database_url: str | None = None,
    *,
    concurrent_requests: int = 20,
) -> dict[str, Any]:
    configured_url = database_url or os.getenv("SOFTWARE_AGENT_DATABASE_URL", "").strip()
    if configured_url:
        return _run(configured_url, concurrent_requests=concurrent_requests)
    with TemporaryDirectory(prefix="software-agent-step34-") as directory:
        path = Path(directory) / "step34.db"
        return _run(
            "sqlite:///" + path.as_posix(),
            concurrent_requests=concurrent_requests,
        )


def _run(database_url: str, *, concurrent_requests: int) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    prefix = f"evo_step34_{run_id}"
    store_a = ControlPlaneStore(database_url)
    store_b = ControlPlaneStore(database_url)
    evolution_a = EvolutionRepository(store=store_a)
    evolution_b = EvolutionRepository(store=store_b)
    policies_a = PolicyRepository(store=store_a)
    policies_b = PolicyRepository(store=store_b)
    bridge_a = EvolutionPolicyBridgeService(evolution=evolution_a, policies=policies_a)
    bridge_b = EvolutionPolicyBridgeService(evolution=evolution_b, policies=policies_b)
    gates: dict[str, bool] = {}
    details: dict[str, Any] = {}

    try:
        same_id = f"{prefix}_same"
        evolution_a.save_candidate(reviewed_candidate(same_id))
        same_results = _concurrent_release(
            [bridge_a, bridge_b],
            same_id,
            request_count=concurrent_requests,
        )
        same_successes = [item for item in same_results if item["ok"]]
        same_policy_ids = {
            item["result"]["policy_id"] for item in same_successes
        }
        same_bridges = [
            item for item in evolution_b.bridges() if item.candidate_id == same_id
        ]
        same_policies = _policies_for_candidate(policies_b, same_id)
        gates["same_candidate_all_requests_succeeded"] = (
            len(same_successes) == concurrent_requests
        )
        gates["same_candidate_one_policy"] = (
            len(same_policy_ids) == len(same_policies) == 1
        )
        gates["same_candidate_one_bridge"] = len(same_bridges) == 1
        gates["same_candidate_one_creator"] = (
            sum(item["result"]["created"] for item in same_successes) == 1
        )
        same_policy_id = next(iter(same_policy_ids))
        _release_service(store_a, evolution_a).rollback(
            same_policy_id,
            reason="Step 34 same-candidate cleanup",
        )

        contender_ids = [f"{prefix}_contender_a", f"{prefix}_contender_b"]
        for candidate_id in contender_ids:
            evolution_a.save_candidate(reviewed_candidate(candidate_id))
        with ThreadPoolExecutor(max_workers=2) as executor:
            contender_futures = [
                executor.submit(
                    _attempt_release,
                    service,
                    candidate_id,
                )
                for service, candidate_id in zip(
                    (bridge_a, bridge_b), contender_ids, strict=True
                )
            ]
        contender_results = [future.result() for future in contender_futures]
        contender_successes = [item for item in contender_results if item["ok"]]
        contender_conflicts = [item for item in contender_results if not item["ok"]]
        gates["different_candidates_single_winner"] = len(contender_successes) == 1
        gates["different_candidates_conflict_is_explicit"] = bool(
            len(contender_conflicts) == 1
            and contender_conflicts[0]["error_type"] == "ValueError"
            and "Another rollout policy" in contender_conflicts[0]["error"]
        )
        winner_policy_id = contender_successes[0]["result"]["policy_id"]
        _release_service(store_a, evolution_a).rollback(
            winner_policy_id,
            reason="Step 34 contender cleanup",
        )

        recovery_id = f"{prefix}_recovery"
        evolution_a.save_candidate(reviewed_candidate(recovery_id))
        failing_evolution = FailOnceEvolutionRepository(store=store_a)
        failing_bridge = EvolutionPolicyBridgeService(
            evolution=failing_evolution,
            policies=policies_a,
        )
        failure_injected = False
        try:
            failing_bridge.release(
                recovery_id,
                rollout_percentage=20,
                released_by="step34-release-owner",
            )
        except InjectedBridgeWriteFailure:
            failure_injected = True
        policy_count_before_retry = len(policies_b.list())
        orphan_before_retry = _orphan_policy_ids(policies_b, evolution_b)
        recovered = bridge_b.release(
            recovery_id,
            rollout_percentage=20,
            released_by="step34-release-owner",
        )
        orphan_after_retry = _orphan_policy_ids(policies_b, evolution_b)
        gates["bridge_write_failure_injected"] = failure_injected
        gates["orphan_window_observed"] = len(orphan_before_retry) == 1
        gates["retry_reuses_existing_policy"] = bool(
            recovered["idempotent_replay"]
            and len(policies_b.list()) == policy_count_before_retry
        )
        gates["retry_repairs_bridge_without_orphan"] = orphan_after_retry == []
        recovery_candidate = evolution_b.get_candidate(recovery_id)
        gates["retry_activates_candidate_after_bridge"] = bool(
            recovery_candidate and recovery_candidate.active
        )
        _release_service(store_a, evolution_a).rollback(
            recovered["policy"]["policy_id"],
            reason="Step 34 recovery cleanup",
        )

        race_id = f"{prefix}_race"
        evolution_a.save_candidate(reviewed_candidate(race_id))
        race_release = bridge_a.release(
            race_id,
            rollout_percentage=20,
            released_by="step34-release-owner",
        )
        race_policy_id = race_release["policy"]["policy_id"]
        race_parent_id = race_release["policy"]["parent_policy_id"]
        release_a = _release_service(store_a, evolution_a)
        release_b = _release_service(store_b, evolution_b)
        with ThreadPoolExecutor(max_workers=2) as executor:
            race_futures = [
                executor.submit(_attempt_policy_action, release_a, "promote", race_policy_id),
                executor.submit(_attempt_policy_action, release_b, "rollback", race_policy_id),
            ]
        race_results = [future.result() for future in race_futures]
        final_policies = PolicyRepository(store=store_a)
        final_state = final_policies.state()
        final_race_policy = final_policies.get(race_policy_id)
        final_race_candidate = evolution_b.get_candidate(race_id)
        gates["promote_rollback_race_is_bounded"] = all(
            item["ok"] or item["error_type"] == "ValueError" for item in race_results
        )
        gates["promote_rollback_race_restores_parent"] = bool(
            final_state["stable_policy_id"] == race_parent_id
            and final_state["rollout_policy_id"] is None
            and final_race_policy
            and final_race_policy.status == "rolled_back"
        )
        gates["promote_rollback_race_deactivates_candidate"] = bool(
            final_race_candidate and not final_race_candidate.active
        )
        gates["final_orphan_policy_count_zero"] = (
            _orphan_policy_ids(final_policies, evolution_b) == []
        )
        gates["database_healthy"] = bool(store_a.status()["healthy"])

        details = {
            "run_id": run_id,
            "same_candidate_requests": concurrent_requests,
            "same_candidate_successes": len(same_successes),
            "same_candidate_policy_ids": sorted(same_policy_ids),
            "different_candidate_outcomes": contender_results,
            "orphan_before_retry": orphan_before_retry,
            "orphan_after_retry": orphan_after_retry,
            "race_outcomes": race_results,
            "final_stable_policy_id": final_state["stable_policy_id"],
            "final_rollout_policy_id": final_state["rollout_policy_id"],
        }
        return {
            "benchmark": "Software-Agent-Step34-Bridge-Fault-Injection",
            "backend": store_a.scheme,
            "independent_store_instances": 2,
            "concurrent_requests": concurrent_requests,
            "gates": gates,
            "passed_gates": sum(gates.values()),
            "total_gates": len(gates),
            "details": details,
            "paid_api_calls": 0,
            "passed": all(gates.values()),
            "bad_cases": [key for key, passed in gates.items() if not passed],
        }
    finally:
        store_a.close()
        store_b.close()


def _concurrent_release(
    services: list[EvolutionPolicyBridgeService],
    candidate_id: str,
    *,
    request_count: int,
) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=min(16, request_count)) as executor:
        futures = [
            executor.submit(
                _attempt_release,
                services[index % len(services)],
                candidate_id,
            )
            for index in range(request_count)
        ]
    return [future.result() for future in futures]


def _attempt_release(
    service: EvolutionPolicyBridgeService,
    candidate_id: str,
) -> dict[str, Any]:
    try:
        released = service.release(
            candidate_id,
            rollout_percentage=20,
            released_by="step34-release-owner",
        )
        return {
            "ok": True,
            "result": {
                "candidate_id": released["bridge"]["candidate_id"],
                "bridge_id": released["bridge"]["bridge_id"],
                "policy_id": released["policy"]["policy_id"],
                "created": released["created"],
                "idempotent_replay": released["idempotent_replay"],
            },
        }
    except Exception as exc:  # noqa: BLE001 - fault harness records exact outcomes
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _attempt_policy_action(
    service: PolicyReleaseService,
    action: str,
    policy_id: str,
) -> dict[str, Any]:
    try:
        result = (
            service.promote(policy_id)
            if action == "promote"
            else service.rollback(policy_id, reason="Step 34 race rollback")
        )
        policy = result.get("policy", result)
        return {
            "action": action,
            "ok": True,
            "result": {
                "policy_id": policy["policy_id"],
                "status": policy["status"],
            },
        }
    except Exception as exc:  # noqa: BLE001 - race harness records legal loser
        return {
            "action": action,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _release_service(
    store: ControlPlaneStore,
    evolution: EvolutionRepository,
) -> PolicyReleaseService:
    policies = PolicyRepository(store=store)
    return PolicyReleaseService(
        repository=policies,
        engine=PolicyEngine(policies, PolicyMonitor(min_samples=1000)),
        candidates=CandidateRepository(),
        evolution_candidates=evolution,
    )


def _policies_for_candidate(
    policies: PolicyRepository,
    candidate_id: str,
) -> list[Any]:
    return [
        item
        for item in policies.list()
        if item.metadata.get("evolution_candidate_id") == candidate_id
    ]


def _orphan_policy_ids(
    policies: PolicyRepository,
    evolution: EvolutionRepository,
) -> list[str]:
    bridge_policy_ids = {item.policy_id for item in evolution.bridges()}
    return sorted(
        item.policy_id
        for item in policies.list()
        if item.source_candidate_id
        and item.source_candidate_id.startswith("evolution:")
        and item.policy_id not in bridge_policy_ids
    )


if __name__ == "__main__":
    report = run_bridge_fault_evaluation()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
