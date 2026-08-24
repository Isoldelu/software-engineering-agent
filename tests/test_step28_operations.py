from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from app.observability.audit_sink import AuditSink
from app.observability.metrics import MetricsRegistry
from app.security.audit import AuditRepository
from app.storage.backup import BackupIntegrityError, ControlPlaneBackupService
from app.storage.database import ControlPlaneStore


def _store(tmp_path, name: str = "step28.db") -> ControlPlaneStore:
    return ControlPlaneStore("sqlite:///" + (tmp_path / name).as_posix())


def test_sqlite_keeps_pool_disabled_and_reports_redacted_status(tmp_path):
    store = _store(tmp_path)
    status = store.status()

    assert status["pool"]["enabled"] is False
    assert status["credentials_exposed"] is False


def test_prometheus_metrics_use_route_templates_and_constant_buckets():
    metrics = MetricsRegistry()
    metrics.observe_request("GET", "/traces/{trace_id}", 200, 0.2)
    metrics.observe_request("GET", "/traces/{trace_id}", 404, 0.4)
    metrics.observe_auth_denial("authorization")
    rendered = metrics.render(storage={"healthy": True, "pool": {"enabled": False}})

    assert 'route="/traces/{trace_id}"' in rendered
    assert 'status="200"' in rendered
    assert 'reason="authorization"' in rendered
    assert "software_agent_storage_healthy 1" in rendered
    assert "trace-secret-value" not in rendered
    assert len(metrics._durations[("GET", "/traces/{trace_id}")].bucket_counts) == 10


def test_independent_audit_sink_is_jsonl_and_rejects_sensitive_fields(tmp_path):
    path = tmp_path / "audit" / "events.jsonl"
    sink = AuditSink(path)
    safe = {
        "event_id": "audit-safe",
        "resource": "/agent/query",
        "details": {"status_code": 200},
    }

    assert sink.emit(safe)
    assert not sink.emit({**safe, "api_key": "forbidden"})
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    assert len(lines) == 1
    assert event["schema_version"] == "audit-event-v1"
    assert "forbidden" not in str(event)


def test_audit_sink_is_attempted_when_database_write_fails(tmp_path):
    path = tmp_path / "independent.jsonl"

    class FailedStore:
        placeholder = "?"

        @contextmanager
        def transaction(self, *, write=False):
            raise RuntimeError("database unavailable")
            yield

    repository = AuditRepository(FailedStore(), sink=AuditSink(path))
    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.record(
            event_type="api_request",
            resource="/ready",
            action="GET",
            outcome="failed",
        )

    assert json.loads(path.read_text(encoding="utf-8"))["outcome"] == "failed"


def test_backup_verify_restore_and_corruption_rejection(tmp_path):
    source = _store(tmp_path, "source.db")
    source.upsert("trace", "trace-a", {"value": 1}, expected_version=0)
    source.upsert("session", "session-a", {"value": 2}, expected_version=0)
    backup_path = tmp_path / "backup.json"
    created = ControlPlaneBackupService(source).create(backup_path)
    target = _store(tmp_path, "target.db")
    service = ControlPlaneBackupService(target)

    verified = service.verify(backup_path)
    restored = service.restore(backup_path, clear_existing=True)

    assert created["record_count"] == 2
    assert created["includes_api_key_registry"] is False
    assert created["includes_audit"] is False
    assert verified["verified"] is True
    assert restored["restored_records"] == 2
    assert target.get("trace", "trace-a").payload == {"value": 1}
    document = json.loads(backup_path.read_text(encoding="utf-8"))
    document["records"][0]["payload"] = {"value": 999}
    backup_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BackupIntegrityError, match="checksum mismatch"):
        service.verify(backup_path)
