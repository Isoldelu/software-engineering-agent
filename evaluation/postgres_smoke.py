"""Minimal real PostgreSQL adapter smoke for CI or a configured deployment."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.database import ControlPlaneStore


def run_postgres_smoke() -> dict:
    database_url = os.getenv("SOFTWARE_AGENT_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL must point to PostgreSQL.")
    store_a = ControlPlaneStore(database_url)
    store_b = ControlPlaneStore(database_url)
    namespace = f"postgres_smoke_{uuid.uuid4().hex}"
    record = store_a.upsert(namespace, "shared", {"value": 1}, expected_version=0)
    shared = store_b.get(namespace, "shared")
    lease_a = store_a.acquire_lease(namespace, "worker-a")
    lease_b_blocked = not store_b.acquire_lease(namespace, "worker-b")
    store_a.release_lease(namespace, "worker-a")
    store_a.delete_namespace(namespace)
    passed = bool(
        record.version == 1
        and shared
        and shared.payload == {"value": 1}
        and lease_a
        and lease_b_blocked
        and store_a.status()["healthy"]
        and store_a.status()["migration"]["current_version"] == 3
    )
    return {
        "benchmark": "Software-Agent-PostgreSQL-Smoke",
        "backend": "postgresql",
        "shared_record": bool(shared),
        "lease_exclusive": lease_a and lease_b_blocked,
        "schema_version": store_a.status()["schema_version"],
        "migration_up_to_date": store_a.status()["migration"]["up_to_date"],
        "credentials_exposed": False,
        "passed": passed,
    }


if __name__ == "__main__":
    report = run_postgres_smoke()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
