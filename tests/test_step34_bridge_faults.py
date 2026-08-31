from __future__ import annotations

import time
from pathlib import Path

from app.evolution.bridge import EvolutionPolicyBridgeService
from app.evolution.repository import EvolutionRepository
from app.maintenance.retention import RetentionService
from app.policy.repository import PolicyRepository
from app.storage.database import ControlPlaneStore
from evaluation.step34_bridge_fault_eval import (
    reviewed_candidate,
    run_bridge_fault_evaluation,
)
from evaluation.step34_bridge_http import prepare_candidate

ROOT = Path(__file__).resolve().parents[1]


def _database_url(tmp_path, name: str = "step34.db") -> str:
    return "sqlite:///" + (tmp_path / name).as_posix()


def test_step34_fault_evaluation_passes_all_database_gates(tmp_path):
    report = run_bridge_fault_evaluation(_database_url(tmp_path))

    assert report["passed"]
    assert report["backend"] == "sqlite"
    assert report["concurrent_requests"] == 20
    assert report["passed_gates"] == report["total_gates"] == 16
    assert report["details"]["same_candidate_successes"] == 20
    assert report["details"]["orphan_before_retry"]
    assert report["details"]["orphan_after_retry"] == []
    assert report["bad_cases"] == []


def test_step34_http_candidate_preparation_is_persistent_and_idempotent(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("SOFTWARE_AGENT_DATABASE_URL", _database_url(tmp_path))

    first = prepare_candidate()
    second = prepare_candidate()

    assert first["created"] is True
    assert second["created"] is False
    assert first["candidate_id"] == second["candidate_id"]
    assert second["status"] == "approved"


def test_retention_never_prunes_bridge_or_policy_release_evidence(tmp_path):
    store = ControlPlaneStore(_database_url(tmp_path))
    evolution = EvolutionRepository(store=store)
    candidate = reviewed_candidate("evo_step34_retention")
    evolution.save_candidate(candidate)
    policies = PolicyRepository(store=store)
    bridge = EvolutionPolicyBridgeService(evolution=evolution, policies=policies)
    released = bridge.release(
        candidate.candidate_id,
        rollout_percentage=20,
        released_by="retention-test",
    )
    old = time.time() - 1000 * 86_400
    with store.transaction(write=True) as cursor:
        cursor.execute(
            "UPDATE control_plane_records SET updated_at = ? "
            "WHERE namespace IN (?, ?)",
            (old, "evolution_policy_bridge", "policy_state"),
        )

    result = RetentionService(store).run(
        dry_run=False,
        batch_limit=1000,
        now=time.time(),
    )

    assert result["protected_namespaces"] == [
        "evolution_policy_bridge",
        "policy_state",
    ]
    assert evolution.get_bridge(released["bridge"]["bridge_id"]) is not None
    assert PolicyRepository(store=store).get(released["policy"]["policy_id"]) is not None
    store.close()


def test_step34_ci_runs_real_postgres_multiworker_bridge_experiment():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "evaluation/step34_bridge_fault_eval.py" in workflow
    assert "evaluation/step34_bridge_http.py --prepare" in workflow
    assert "Step 34 two-worker concurrent Bridge release" in workflow
    assert "software-agent-step34-bridge-evidence" in workflow
    assert "--requests 20" in workflow
    assert "--concurrency 8" in workflow


def test_step34_eval_runner_exposes_bridge_fault_suite():
    source = (ROOT / "evaluation" / "eval_runner.py").read_text(encoding="utf-8")

    assert '"bridge-fault"' in source
    assert '"bridge_fault_injection": run_bridge_fault_evaluation()' in source
