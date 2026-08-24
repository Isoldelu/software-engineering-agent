from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.evolution.models import EvolutionCandidate
from app.evolution.repository import EvolutionRepository
from app.feedback.models import FeedbackRecord
from app.feedback.repository import FeedbackRepository
from app.policy.repository import PolicyRepository
from app.security.api_key import (
    ApiKeyAuthenticator,
    AuthenticationError,
    AuthorizationError,
    AuthSettings,
    required_role,
)
from app.storage.database import ConcurrentUpdateError, ControlPlaneStore


def _database_url(tmp_path) -> str:
    return "sqlite:///" + (tmp_path / "control-plane.db").as_posix()


def test_shared_store_persists_records_across_independent_instances(tmp_path):
    url = _database_url(tmp_path)
    writer = ControlPlaneStore(url)
    reader = ControlPlaneStore(url)

    created = writer.upsert("test", "record", {"value": 1}, expected_version=0)
    loaded = reader.get("test", "record")

    assert created.version == 1
    assert loaded and loaded.payload == {"value": 1}
    assert loaded.version == 1


def test_compare_and_swap_rejects_stale_worker_update(tmp_path):
    store_a = ControlPlaneStore(_database_url(tmp_path))
    store_b = ControlPlaneStore(_database_url(tmp_path))
    first = store_a.upsert("test", "record", {"worker": "initial"}, expected_version=0)
    stale = store_b.get("test", "record")

    store_a.upsert("test", "record", {"worker": "a"}, expected_version=first.version)
    with pytest.raises(ConcurrentUpdateError, match="Revision conflict"):
        store_b.upsert(
            "test",
            "record",
            {"worker": "b"},
            expected_version=stale.version if stale else 0,
        )


def test_database_lease_is_exclusive_and_recoverable(tmp_path):
    store_a = ControlPlaneStore(_database_url(tmp_path))
    store_b = ControlPlaneStore(_database_url(tmp_path))

    assert store_a.acquire_lease("policy", "worker-a", ttl_seconds=10)
    assert not store_b.acquire_lease("policy", "worker-b", ttl_seconds=10)
    assert store_a.release_lease("policy", "worker-a")
    assert store_b.acquire_lease("policy", "worker-b", ttl_seconds=10)


def test_trace_is_visible_to_another_repository_process(tmp_path):
    url = _database_url(tmp_path)
    writer = TraceRepository(store=ControlPlaneStore(url))
    reader = TraceRepository(store=ControlPlaneStore(url))
    trace = {"trace_id": "tr_shared", "input": {"resolved_query": "openssl"}}

    persistence = writer.save(trace)

    assert persistence["backend"] == "sqlite"
    assert reader.get("tr_shared") == trace


def test_feedback_is_visible_to_another_repository_process(tmp_path):
    url = _database_url(tmp_path)
    writer = FeedbackRepository(store=ControlPlaneStore(url))
    reader = FeedbackRepository(store=ControlPlaneStore(url))
    feedback = FeedbackRecord(
        feedback_id="fb_shared",
        trace_id="tr_shared",
        rating=-1,
        issue_type="wrong_tool",
        expected_tool="dependency_analysis",
        comment="shared feedback",
        status="open",
        fingerprint="wrong_tool:dependency_analysis:prerequisites",
        observed={"selected_tool": "package_search"},
        created_at="now",
    )

    writer.save(feedback)

    assert reader.get(feedback.feedback_id) == feedback


def test_session_context_is_visible_to_another_repository_process(tmp_path):
    url = _database_url(tmp_path)
    writer = SessionRepository(store=ControlPlaneStore(url))
    reader = SessionRepository(store=ControlPlaneStore(url))
    context = writer.get_or_create("shared-session")
    context.packages = ["openssl"]
    context.turn_count = 1
    writer.save(context)

    loaded = reader.get("shared-session")

    assert loaded and loaded.packages == ["openssl"]
    assert loaded.turn_count == 1


def test_evolution_candidate_cas_blocks_double_review(tmp_path):
    url = _database_url(tmp_path)
    repo_a = EvolutionRepository(store=ControlPlaneStore(url))
    candidate = EvolutionCandidate(
        candidate_id="evo_shared",
        schema_version="evolution-candidate-v1",
        asset_type="query_alias",
        status="pending_review",
        source_cluster_id="cluster",
        source_failure_ids=["failure"],
        config={"aliases": {"tls toolkit": "openssl"}},
        safety_scope={"automatic_activation": False, "requires_human_review": True},
        created_at="now",
    )
    repo_a.save_candidate(candidate)
    repo_b = EvolutionRepository(store=ControlPlaneStore(url))
    worker_a = repo_a.get_candidate(candidate.candidate_id)
    worker_b = repo_b.get_candidate(candidate.candidate_id)
    assert worker_a and worker_b

    worker_a.status = "approved"
    repo_a.save_candidate(worker_a)
    worker_b.status = "rejected"
    with pytest.raises(ConcurrentUpdateError):
        repo_b.save_candidate(worker_b)


def test_policy_versions_are_unique_across_concurrent_repositories(tmp_path):
    url = _database_url(tmp_path)
    repo_a = PolicyRepository(store=ControlPlaneStore(url))
    repo_b = PolicyRepository(store=ControlPlaneStore(url))

    def create(repository: PolicyRepository, source: str):
        return repository.create(config={"rules": []}, source_candidate_id=source)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create, repo_a, "candidate-a"),
            executor.submit(create, repo_b, "candidate-b"),
        ]
    policies = [future.result() for future in futures]

    assert {item.version for item in policies} == {2, 3}
    assert {item.policy_id for item in policies} == {"policy_v2", "policy_v3"}
    assert len(repo_a.list()) == 3
    assert len(repo_b.list()) == 3


def test_api_key_role_hierarchy_and_secret_redaction():
    settings = AuthSettings(
        enabled=True,
        keys={"reader": "read-key", "operator": "operate-key", "admin": "admin-key"},
    )
    authenticator = ApiKeyAuthenticator()

    assert authenticator.authenticate(
        "admin-key", required_role="reader", settings=settings
    ).role == "admin"
    with pytest.raises(AuthorizationError):
        authenticator.authenticate("read-key", required_role="operator", settings=settings)
    status = settings.public_status()
    assert status["secrets_exposed"] is False
    assert "read-key" not in str(status)


def test_route_policy_assigns_reader_operator_admin_and_public_access():
    assert required_role("GET", "/health") is None
    assert required_role("GET", "/auth/status") is None
    assert required_role("GET", "/tools") == "reader"
    assert required_role("POST", "/agent/query") == "operator"
    assert required_role("POST", "/evolution/scan") == "operator"
    assert required_role("POST", "/evolution/candidates/evo/review") == "admin"
    assert required_role("POST", "/policies/policy_v2/rollback") == "admin"
    assert required_role("GET", "/auth/keys") == "admin"
    assert required_role("POST", "/maintenance/retention/run") == "admin"
    assert required_role("DELETE", "/sessions/session") == "admin"


def test_authentication_fails_closed_and_is_disabled_by_default():
    authenticator = ApiKeyAuthenticator()
    enabled = AuthSettings(enabled=True, keys={"reader": "read-key"})

    with pytest.raises(AuthenticationError):
        authenticator.authenticate(None, required_role="reader", settings=enabled)
    principal = authenticator.authenticate(
        None,
        required_role="admin",
        settings=AuthSettings(enabled=False, keys={}),
    )
    assert principal.authentication_enabled is False
    assert principal.role == "anonymous"


def test_delivery_config_declares_postgres_auth_and_multiple_workers():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    runtime = (root / "requirements-runtime.txt").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "postgres:16-alpine" in compose
    assert "SOFTWARE_AGENT_DATABASE_URL" in compose
    assert '"--workers", "2"' in compose
    assert "SOFTWARE_AGENT_ADMIN_API_KEY" in compose
    assert "psycopg[binary,pool]" in runtime
    assert "prometheus-client" in runtime
    assert "postgres-integration" in workflow
    assert "evaluation/postgres_smoke.py" in workflow
    assert "evaluation/step27_load.py" in workflow
    assert "evaluation/step27_fault_eval.py" in workflow
    assert "Kill one worker" in workflow
    assert "PostgreSQL outage" in workflow
    assert "evaluation/backup_restore_drill.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "PROMETHEUS_MULTIPROC_DIR" in workflow
    assert "SOFTWARE_AGENT_AUDIT_LOG_PATH" in workflow
