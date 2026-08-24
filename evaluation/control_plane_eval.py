"""Evaluate Step 26 persistence, authorization, and multi-worker consistency."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.evolution.models import EvolutionCandidate
from app.evolution.repository import EvolutionRepository
from app.feedback.models import FeedbackRecord
from app.feedback.repository import FeedbackRepository
from app.policy.repository import PolicyRepository
from app.security.api_key import ApiKeyAuthenticator, AuthorizationError, AuthSettings
from app.storage.database import ConcurrentUpdateError, ControlPlaneStore


def run_control_plane_evaluation() -> dict[str, Any]:
    with TemporaryDirectory(prefix="software-agent-step26-") as directory:
        database_path = Path(directory) / "control-plane.db"
        database_url = "sqlite:///" + database_path.as_posix()
        store_a = ControlPlaneStore(database_url)
        store_b = ControlPlaneStore(database_url)

        created = store_a.upsert("probe", "shared", {"worker": "a"}, expected_version=0)
        shared = store_b.get("probe", "shared")
        stale = store_b.get("probe", "shared")
        store_a.upsert(
            "probe", "shared", {"worker": "new"}, expected_version=created.version
        )
        cas_conflict = False
        try:
            store_b.upsert(
                "probe",
                "shared",
                {"worker": "stale"},
                expected_version=stale.version if stale else 0,
            )
        except ConcurrentUpdateError:
            cas_conflict = True

        lease_exclusive = store_a.acquire_lease("evaluation", "worker-a")
        lease_exclusive = lease_exclusive and not store_b.acquire_lease(
            "evaluation", "worker-b"
        )
        store_a.release_lease("evaluation", "worker-a")
        lease_recovered = store_b.acquire_lease("evaluation", "worker-b")
        store_b.release_lease("evaluation", "worker-b")

        trace_writer = TraceRepository(store=store_a)
        trace_reader = TraceRepository(store=store_b)
        trace_writer.save({"trace_id": "tr_step26", "input": {"query": "openssl"}})
        trace_shared = trace_reader.get("tr_step26") is not None

        feedback_writer = FeedbackRepository(store=store_a)
        feedback_reader = FeedbackRepository(store=store_b)
        feedback = FeedbackRecord(
            feedback_id="fb_step26",
            trace_id="tr_step26",
            rating=-1,
            issue_type="wrong_tool",
            expected_tool="dependency_analysis",
            comment="step26",
            status="open",
            fingerprint="wrong_tool:dependency_analysis:prerequisites",
            observed={"selected_tool": "package_search"},
            created_at="now",
        )
        feedback_writer.save(feedback)
        feedback_shared = feedback_reader.get(feedback.feedback_id) == feedback

        session_writer = SessionRepository(store=store_a)
        session_reader = SessionRepository(store=store_b)
        context = session_writer.get_or_create("session-step26")
        context.packages = ["openssl"]
        context.turn_count = 1
        session_writer.save(context)
        shared_context = session_reader.get("session-step26")
        session_shared = bool(
            shared_context
            and shared_context.packages == ["openssl"]
            and shared_context.turn_count == 1
        )

        evolution_a = EvolutionRepository(store=store_a)
        evolution_b = EvolutionRepository(store=store_b)
        candidate = EvolutionCandidate(
            candidate_id="evo_step26",
            schema_version="evolution-candidate-v1",
            asset_type="query_alias",
            status="pending_review",
            source_cluster_id="cluster",
            source_failure_ids=["failure"],
            config={"aliases": {"tls toolkit": "openssl"}},
            safety_scope={"automatic_activation": False, "requires_human_review": True},
            created_at="now",
        )
        evolution_a.save_candidate(candidate)
        candidate_a = evolution_a.get_candidate(candidate.candidate_id)
        candidate_b = evolution_b.get_candidate(candidate.candidate_id)
        evolution_cas_conflict = False
        if candidate_a and candidate_b:
            candidate_a.status = "approved"
            evolution_a.save_candidate(candidate_a)
            candidate_b.status = "rejected"
            try:
                evolution_b.save_candidate(candidate_b)
            except ConcurrentUpdateError:
                evolution_cas_conflict = True

        policy_a = PolicyRepository(store=store_a)
        policy_b = PolicyRepository(store=store_b)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    policy_a.create,
                    config={"rules": []},
                    source_candidate_id="candidate-a",
                ),
                executor.submit(
                    policy_b.create,
                    config={"rules": []},
                    source_candidate_id="candidate-b",
                ),
            ]
        created_policies = [future.result() for future in futures]
        policy_versions_unique = {item.version for item in created_policies} == {2, 3}
        policy_cross_worker_visible = len(policy_a.list()) == len(policy_b.list()) == 3

        auth = ApiKeyAuthenticator()
        settings = AuthSettings(
            enabled=True,
            keys={"reader": "read-key", "operator": "operate-key", "admin": "admin-key"},
        )
        admin_can_read = auth.authenticate(
            "admin-key", required_role="reader", settings=settings
        ).role == "admin"
        reader_blocked = False
        try:
            auth.authenticate("read-key", required_role="operator", settings=settings)
        except AuthorizationError:
            reader_blocked = True
        redacted = settings.public_status()["secrets_exposed"] is False

        thresholds = {
            "shared_record_visible": bool(shared and shared.payload["worker"] == "a"),
            "stale_revision_rejected": cas_conflict,
            "lease_exclusive": lease_exclusive,
            "lease_recoverable": lease_recovered,
            "trace_cross_worker_visible": trace_shared,
            "feedback_cross_worker_visible": feedback_shared,
            "session_cross_worker_visible": session_shared,
            "evolution_double_review_rejected": evolution_cas_conflict,
            "policy_versions_unique": policy_versions_unique,
            "policy_cross_worker_visible": policy_cross_worker_visible,
            "auth_role_hierarchy": admin_can_read and reader_blocked,
            "auth_secrets_redacted": redacted,
            "database_healthy": store_a.status()["healthy"],
        }
        return {
            "benchmark": "Software-Agent-Control-Plane",
            "backend_under_test": "sqlite_wal",
            "deployment_backend": "postgresql",
            "independent_store_instances": 2,
            "policy_versions": sorted(item.version for item in created_policies),
            "thresholds": thresholds,
            "paid_api_calls": 0,
            "passed": all(thresholds.values()),
            "bad_cases": [key for key, value in thresholds.items() if not value],
        }


if __name__ == "__main__":
    print(json.dumps(run_control_plane_evaluation(), ensure_ascii=False, indent=2))
