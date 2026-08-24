from __future__ import annotations

import sqlite3
import time

import pytest

from app.maintenance.retention import DAY_SECONDS, RetentionService
from app.security.api_key import ApiKeyAuthenticator, AuthenticationError, AuthSettings
from app.security.audit import AuditRepository
from app.security.key_registry import KeyRegistry
from app.storage.database import ControlPlaneStore
from app.storage.migrations import LATEST_SCHEMA_VERSION, MigrationChecksumError


def _store(tmp_path) -> ControlPlaneStore:
    url = "sqlite:///" + (tmp_path / "step27.db").as_posix()
    return ControlPlaneStore(url)


def test_migrations_are_idempotent_and_report_latest_version(tmp_path):
    store = _store(tmp_path)
    reopened = ControlPlaneStore(store.database_url)

    assert store.migration_status["applied_now"] == [1, 2, 3]
    assert reopened.migration_status["applied_now"] == []
    assert reopened.status()["migration"]["current_version"] == LATEST_SCHEMA_VERSION


def test_step26_legacy_schema_is_adopted_without_data_loss(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE control_plane_records ("
            "namespace TEXT NOT NULL, record_id TEXT NOT NULL, payload TEXT NOT NULL, "
            "version INTEGER NOT NULL, updated_at DOUBLE PRECISION NOT NULL, "
            "PRIMARY KEY (namespace, record_id))"
        )
        connection.execute(
            "CREATE TABLE control_plane_leases ("
            "name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL)"
        )
        connection.execute(
            "INSERT INTO control_plane_records VALUES (?, ?, ?, ?, ?)",
            ("trace", "legacy", '{"trace_id":"legacy"}', 1, time.time()),
        )

    store = ControlPlaneStore("sqlite:///" + path.as_posix())

    assert store.get("trace", "legacy").payload == {"trace_id": "legacy"}
    assert store.migration_status["applied_now"] == [1, 2, 3]


def test_migration_checksum_drift_fails_closed(tmp_path):
    store = _store(tmp_path)
    with store.transaction(write=True) as cursor:
        cursor.execute(
            "UPDATE control_plane_schema_migrations SET checksum = ? WHERE version = ?",
            ("tampered", 2),
        )

    with pytest.raises(MigrationChecksumError, match="checksum/name mismatch"):
        ControlPlaneStore(store.database_url)


def test_database_key_rotation_grace_and_revocation(tmp_path):
    store = _store(tmp_path)
    registry = KeyRegistry(store, pepper="test-pepper")
    first = registry.rotate("admin", actor="bootstrap", grace_seconds=0)
    second = registry.rotate("admin", actor="admin", grace_seconds=30)

    assert registry.authenticate(second["api_key"]).role == "admin"
    assert registry.authenticate(first["api_key"]).status == "grace"
    revoked = registry.revoke(first["key_id"], actor="admin")
    assert revoked.status == "revoked"
    assert registry.authenticate(first["api_key"]) is None
    assert "api_key" not in str(registry.list(include_expired=True))
    assert "secret_hash" not in str(registry.list(include_expired=True))


def test_managed_role_replaces_environment_key_across_authenticators(tmp_path):
    store = _store(tmp_path)
    registry = KeyRegistry(store)
    rotated = registry.rotate("operator", actor="admin")
    settings = AuthSettings(enabled=True, keys={"operator": "legacy-operator"})

    with pytest.raises(AuthenticationError):
        ApiKeyAuthenticator(store).authenticate(
            "legacy-operator", required_role="operator", settings=settings
        )
    principal = ApiKeyAuthenticator(ControlPlaneStore(store.database_url)).authenticate(
        rotated["api_key"], required_role="operator", settings=settings
    )
    assert principal.role == "operator"


def test_audit_events_are_structured_and_do_not_store_raw_key(tmp_path):
    audit = AuditRepository(_store(tmp_path))
    raw_key = "must-never-be-persisted"
    event = audit.record(
        event_type="authentication",
        resource="/agent/query",
        action="POST",
        outcome="success",
        actor_fingerprint="abc123",
        actor_role="operator",
        details={"status_code": 200},
    )
    events = audit.list()

    assert events[0]["event_id"] == event["event_id"]
    assert events[0]["actor_fingerprint"] == "abc123"
    assert raw_key not in str(events)


def test_retention_supports_dry_run_bounded_delete_and_audit_prune(tmp_path, monkeypatch):
    store = _store(tmp_path)
    audit = AuditRepository(store)
    now = time.time()
    old = now - 31 * DAY_SECONDS
    store.upsert("trace", "old-a", {"trace_id": "old-a"})
    store.upsert("trace", "old-b", {"trace_id": "old-b"})
    store.upsert("trace", "new", {"trace_id": "new"})
    audit.record(
        event_type="api_request",
        resource="/tools",
        action="GET",
        outcome="success",
    )
    with store.transaction(write=True) as cursor:
        cursor.execute(
            "UPDATE control_plane_records SET updated_at = ? "
            "WHERE namespace = ? AND record_id IN (?, ?)",
            (old, "trace", "old-a", "old-b"),
        )
        cursor.execute("UPDATE control_plane_audit SET created_at = ?", (old,))
    monkeypatch.setenv("SOFTWARE_AGENT_RETENTION_AUDIT_DAYS", "30")
    service = RetentionService(store)

    preview = service.run(dry_run=True, batch_limit=1, now=now)
    executed = service.run(dry_run=False, batch_limit=1, now=now)

    assert preview["total_affected"] == 2
    assert executed["total_affected"] == 2
    assert store.get("trace", "old-a") is None
    assert store.get("trace", "old-b") is not None
    assert store.get("trace", "new") is not None
    assert audit.list() == []
