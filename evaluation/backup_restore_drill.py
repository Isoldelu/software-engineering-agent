"""Portable backup/restore drill for SQLite locally and PostgreSQL in CI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.backup import ControlPlaneBackupService
from app.storage.database import ControlPlaneStore


def run_drill() -> dict:
    database_url = os.getenv("SOFTWARE_AGENT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL is required.")
    store = ControlPlaneStore(database_url)
    service = ControlPlaneBackupService(store)
    namespace = f"backup_drill_{uuid.uuid4().hex}"
    try:
        store.upsert(namespace, "record-a", {"value": 1}, expected_version=0)
        store.upsert(namespace, "record-b", {"value": 2}, expected_version=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control-plane-backup.json"
            created = service.create(path, namespaces=[namespace])
            verified = service.verify(path)
            deleted = store.delete_namespace(namespace)
            restored = service.restore(path, clear_existing=True)
            values = {
                item.record_id: item.payload for item in store.list(namespace)
            }
        passed = bool(
            created["record_count"] == 2
            and verified["verified"]
            and deleted == 2
            and restored["restored_records"] == 2
            and values == {"record-a": {"value": 1}, "record-b": {"value": 2}}
        )
        return {
            "benchmark": "Software-Agent-Step28-Backup-Restore-Drill",
            "backend": store.scheme,
            "backup_verified": verified["verified"],
            "records_deleted": deleted,
            "records_restored": restored["restored_records"],
            "api_keys_included": created["includes_api_key_registry"],
            "audit_included": created["includes_audit"],
            "passed": passed,
        }
    finally:
        store.delete_namespace(namespace)
        store.close()


if __name__ == "__main__":
    report = run_drill()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
