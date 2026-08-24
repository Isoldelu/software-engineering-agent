"""Evaluate policy versioning, deterministic rollout, monitoring, and rollback."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_GUARD_PATHS = [
    PROJECT_ROOT / "app" / "agent" / "router.py",
    PROJECT_ROOT / "app" / "agent" / "planner.py",
    PROJECT_ROOT / "app" / "agent" / "workflow.py",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.feedback.models import PolicyCandidate
from app.feedback.repository import CandidateRepository
from app.policy.engine import PolicyEngine
from app.policy.monitor import PolicyMonitor
from app.policy.repository import BASE_POLICY_ID, PolicyRepository
from app.policy.service import PolicyReleaseService


def run_policy_evaluation() -> dict[str, Any]:
    source_hash_before = _source_hash()
    candidates = CandidateRepository()
    candidate = _approved_candidate()
    candidates.save(candidate)
    repository = PolicyRepository()
    monitor = PolicyMonitor(min_samples=5)
    engine = PolicyEngine(repository, monitor)
    service = PolicyReleaseService(
        repository=repository,
        engine=engine,
        candidates=candidates,
    )
    release = service.release_candidate(
        candidate.candidate_id,
        rollout_percentage=20,
        released_by="policy-evaluation",
    )
    policy_id = release["policy"]["policy_id"]

    assignments = [engine.assign(f"rollout-eval-{index}") for index in range(1000)]
    rollout_assignments = [item for item in assignments if item.cohort == "rollout"]
    control_assignments = [item for item in assignments if item.cohort == "control"]
    observed_rollout_rate = len(rollout_assignments) / len(assignments)
    stable_hash = all(
        engine.assign(f"stable-{index}").policy_id == engine.assign(f"stable-{index}").policy_id
        and engine.assign(f"stable-{index}").bucket == engine.assign(f"stable-{index}").bucket
        for index in range(100)
    )

    rollout_session = _find_session(engine, "rollout")
    control_session = _find_session(engine, "control")
    traces = TraceRepository(max_records=50)
    rollout_result = run_agent(
        "openssl prerequisites",
        persist_trajectory=False,
        session_id=rollout_session,
        session_repository=SessionRepository(),
        trace_repository=traces,
        policy_engine=engine,
    )
    control_result = run_agent(
        "openssl prerequisites",
        persist_trajectory=False,
        session_id=control_session,
        session_repository=SessionRepository(),
        trace_repository=traces,
        policy_engine=engine,
    )
    historical_trace = traces.get(rollout_result["trace_id"])

    rollback_event = None
    for _ in range(10):
        service.record_monitor_sample(BASE_POLICY_ID, success=True, latency_ms=1.0)
        response = service.record_monitor_sample(policy_id, success=False, latency_ms=1.0)
        rollback_event = response.get("event") or rollback_event
        if repository.rollout_policy_id is None:
            break
    source_hash_after = _source_hash()
    post_rollback_assignment = engine.assign(rollout_session)
    candidate_after = candidates.get(candidate.candidate_id)

    thresholds = {
        "stable_hash_assignment": stable_hash,
        "rollout_distribution": 0.15 <= observed_rollout_rate <= 0.25,
        "control_uses_v1": control_result["policy_version"] == BASE_POLICY_ID,
        "rollout_uses_v2": rollout_result["policy_version"] == policy_id,
        "rollout_rule_effective": rollout_result["selected_tool"] == "dependency_analysis",
        "control_behavior_unchanged": control_result["selected_tool"] == "package_search",
        "historical_trace_policy_locatable": historical_trace["policy_version"] == policy_id,
        "automatic_rollback": repository.rollout_policy_id is None,
        "stable_policy_restored": repository.stable_policy_id == BASE_POLICY_ID,
        "post_rollback_assignment_v1": post_rollback_assignment.policy_id == BASE_POLICY_ID,
        "rollback_without_source_change": source_hash_before == source_hash_after,
        "candidate_deactivated": candidate_after is not None and not candidate_after.active,
    }
    return {
        "benchmark": "Software-Agent-Policy-Rollout-Rollback",
        "policy_id": policy_id,
        "rollout_percentage": 20.0,
        "assignment_samples": len(assignments),
        "rollout_assignments": len(rollout_assignments),
        "control_assignments": len(control_assignments),
        "observed_rollout_rate": observed_rollout_rate,
        "stable_hash_assignment": stable_hash,
        "control": {
            "session_id": control_session,
            "policy_version": control_result["policy_version"],
            "selected_tool": control_result["selected_tool"],
        },
        "rollout": {
            "session_id": rollout_session,
            "policy_version": rollout_result["policy_version"],
            "selected_tool": rollout_result["selected_tool"],
            "trace_id": rollout_result["trace_id"],
        },
        "rollback_event": rollback_event,
        "post_rollback_state": repository.state(),
        "source_hash_before": source_hash_before,
        "source_hash_after": source_hash_after,
        "thresholds": thresholds,
        "passed": all(thresholds.values()),
        "bad_cases": [key for key, passed in thresholds.items() if not passed],
    }


def _approved_candidate() -> PolicyCandidate:
    return PolicyCandidate(
        candidate_id="candidate-policy-eval",
        schema_version="policy-candidate-v1",
        asset_type="router_hook",
        status="approved",
        source_feedback_ids=["fb-1", "fb-2", "fb-3"],
        fingerprint="wrong_tool:dependency_analysis:prerequisites",
        config={
            "rules": [{
                "hook_id": "hook_prerequisites_dependency_analysis",
                "match": {"terms": ["prerequisites"], "mode": "any"},
                "action": {"intent": "dependency_analysis", "tool": "dependency_analysis"},
                "priority": 100,
            }],
        },
        safety_scope={
            "allowed_changes": ["router_hook_config"],
            "forbidden_changes": [
                "python_source", "datasets", "test_assertions", "permissions", "release_gates"
            ],
            "automatic_activation": False,
        },
        created_at="evaluation",
        evaluation={"passed": True},
        review={"decision": "approve", "reviewer": "evaluation"},
        active=False,
    )


def _find_session(engine: PolicyEngine, cohort: str) -> str:
    for index in range(10000):
        session_id = f"{cohort}-session-{index}"
        if engine.assign(session_id).cohort == cohort:
            return session_id
    raise RuntimeError(f"Could not find session for cohort {cohort}")


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in SOURCE_GUARD_PATHS:
        digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    print(json.dumps(run_policy_evaluation(), ensure_ascii=False, indent=2))
