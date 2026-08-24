"""Transactional fault-injection gates for the configured control-plane database."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.database import ConcurrentUpdateError, ControlPlaneStore
from app.storage.migrations import LATEST_SCHEMA_VERSION


def run_fault_evaluation() -> dict:
    database_url = os.getenv("SOFTWARE_AGENT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL is required.")
    store_a = ControlPlaneStore(database_url)
    store_b = ControlPlaneStore(database_url)
    namespace = f"step27_fault_{uuid.uuid4().hex}"
    gates: dict[str, bool] = {}
    try:
        initial = store_a.upsert(namespace, "record", {"value": 1}, expected_version=0)
        store_a.upsert(
            namespace, "record", {"value": 2}, expected_version=initial.version
        )
        try:
            store_b.upsert(
                namespace, "record", {"value": 3}, expected_version=initial.version
            )
            gates["stale_cas_rejected"] = False
        except ConcurrentUpdateError:
            gates["stale_cas_rejected"] = True

        lease_name = f"{namespace}:lease"
        gates["lease_contention_rejected"] = bool(
            store_a.acquire_lease(lease_name, "worker-a", ttl_seconds=0.05)
            and not store_b.acquire_lease(lease_name, "worker-b", ttl_seconds=1)
        )
        time.sleep(0.08)
        gates["expired_lease_recovered"] = store_b.acquire_lease(
            lease_name, "worker-b", ttl_seconds=1
        )
        store_b.release_lease(lease_name, "worker-b")

        marker = store_a.placeholder
        try:
            with store_a.transaction(write=True) as cursor:
                cursor.execute(
                    f"UPDATE control_plane_records SET payload = {marker} "
                    f"WHERE namespace = {marker} AND record_id = {marker}",
                    (json.dumps({"value": 999}), namespace, "record"),
                )
                raise RuntimeError("injected transaction failure")
        except RuntimeError:
            pass
        recovered = store_b.get(namespace, "record")
        gates["failed_transaction_rolled_back"] = bool(
            recovered and recovered.payload == {"value": 2}
        )
        status = store_a.status()
        gates["schema_at_latest_version"] = bool(
            status["migration"]["current_version"] == LATEST_SCHEMA_VERSION
        )
        gates["database_healthy"] = bool(status["healthy"])
    finally:
        store_a.delete_namespace(namespace)
    passed = all(gates.values())
    return {
        "benchmark": "Software-Agent-Step27-Fault-Injection",
        "backend": store_a.scheme,
        "gates": gates,
        "passed_gates": sum(gates.values()),
        "total_gates": len(gates),
        "passed": passed,
    }


if __name__ == "__main__":
    report = run_fault_evaluation()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
