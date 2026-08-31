"""Prepare and run the Step 34 real multi-worker Bridge HTTP experiment."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evolution.repository import EvolutionRepository
from app.policy.repository import PolicyRepository
from app.security.audit import AuditRepository
from app.storage.database import ControlPlaneStore
from evaluation.step34_bridge_fault_eval import reviewed_candidate

DEFAULT_CANDIDATE_ID = "evo_step34_http_multiworker"


def prepare_candidate(candidate_id: str = DEFAULT_CANDIDATE_ID) -> dict[str, Any]:
    store = _configured_store()
    evolution = EvolutionRepository(store=store)
    try:
        existing = evolution.get_candidate(candidate_id)
        if existing:
            return {
                "candidate_id": candidate_id,
                "created": False,
                "status": existing.status,
                "backend": store.scheme,
            }
        candidate = evolution.save_candidate(reviewed_candidate(candidate_id))
        return {
            "candidate_id": candidate_id,
            "created": True,
            "status": candidate.status,
            "backend": store.scheme,
        }
    finally:
        store.close()


def run_http_experiment(
    base_url: str,
    api_key: str,
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    requests: int = 20,
    concurrency: int = 8,
    timeout: float = 20.0,
) -> dict[str, Any]:
    started = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                _release_request,
                base_url,
                api_key,
                candidate_id,
                timeout,
            )
            for _ in range(requests)
        ]
        results = [future.result() for future in as_completed(futures)]

    successes = [item for item in results if item["status"] == 200]
    server_errors = sum(item["status"] >= 500 for item in results)
    policy_ids = {
        item["policy_id"] for item in successes if item.get("policy_id")
    }
    worker_pids = sorted(
        {item["worker_pid"] for item in results if item.get("worker_pid")}
    )
    created_count = sum(bool(item.get("created")) for item in successes)
    replay_count = sum(bool(item.get("idempotent_replay")) for item in successes)
    policy_id = next(iter(policy_ids), None)
    rollback = (
        _json_request(
            f"{base_url.rstrip('/')}/policies/{policy_id}/rollback",
            api_key,
            method="POST",
            body={"reason": "Step 34 HTTP cleanup"},
            timeout=timeout,
        )
        if policy_id
        else {"status": 0, "payload": {}}
    )

    store = _configured_store()
    try:
        evolution = EvolutionRepository(store=store)
        policies = PolicyRepository(store=store)
        bridges = [
            item for item in evolution.bridges() if item.candidate_id == candidate_id
        ]
        candidate_policies = [
            item
            for item in policies.list()
            if item.metadata.get("evolution_candidate_id") == candidate_id
        ]
        candidate = evolution.get_candidate(candidate_id)
        audit_events = [
            item
            for item in AuditRepository(store).list(limit=1000, since=started - 1)
            if item["event_type"] == "evolution_policy_bridge"
            and item["resource"] == candidate_id
        ]
        bridge_policy_ids = {item.policy_id for item in evolution.bridges()}
        orphan_policy_ids = sorted(
            item.policy_id
            for item in policies.list()
            if item.source_candidate_id
            and item.source_candidate_id.startswith("evolution:")
            and item.policy_id not in bridge_policy_ids
        )
        final_state = policies.state()
    finally:
        store.close()

    gates = {
        "all_http_requests_succeeded": len(successes) == requests,
        "server_errors_zero": server_errors == 0,
        "two_workers_observed": len(worker_pids) >= 2,
        "one_policy_id_returned": len(policy_ids) == 1,
        "one_request_created_policy": created_count == 1,
        "remaining_requests_are_idempotent": replay_count == requests - 1,
        "one_persisted_policy": len(candidate_policies) == 1,
        "one_persisted_bridge": len(bridges) == 1,
        "orphan_policy_count_zero": orphan_policy_ids == [],
        "bridge_audit_coverage_complete": len(audit_events) == requests,
        "bridge_audit_role_is_admin": all(
            item["actor_role"] == "admin" for item in audit_events
        ),
        "audit_does_not_expose_api_key": api_key not in json.dumps(audit_events),
        "rollback_succeeded": rollback["status"] == 200,
        "rollback_restored_stable_state": bool(
            final_state["rollout_policy_id"] is None
            and candidate
            and not candidate.active
            and candidate.review.get("activation_status") == "rolled_back"
        ),
    }
    return {
        "benchmark": "Software-Agent-Step34-MultiWorker-Bridge-HTTP",
        "candidate_id": candidate_id,
        "requests": requests,
        "concurrency": concurrency,
        "successes": len(successes),
        "server_errors": server_errors,
        "worker_pids": worker_pids,
        "worker_count_observed": len(worker_pids),
        "policy_ids": sorted(policy_ids),
        "created_count": created_count,
        "idempotent_replay_count": replay_count,
        "bridge_audit_event_count": len(audit_events),
        "orphan_policy_ids": orphan_policy_ids,
        "gates": gates,
        "passed_gates": sum(gates.values()),
        "total_gates": len(gates),
        "paid_api_calls": 0,
        "passed": all(gates.values()),
        "bad_cases": [key for key, passed in gates.items() if not passed],
    }


def _release_request(
    base_url: str,
    api_key: str,
    candidate_id: str,
    timeout: float,
) -> dict[str, Any]:
    response = _json_request(
        f"{base_url.rstrip('/')}/policies/from-evolution/{candidate_id}",
        api_key,
        method="POST",
        body={"rollout_percentage": 20, "released_by": "step34-http-owner"},
        timeout=timeout,
    )
    payload = response["payload"]
    return {
        "status": response["status"],
        "worker_pid": response.get("worker_pid"),
        "policy_id": payload.get("policy", {}).get("policy_id"),
        "created": payload.get("created", False),
        "idempotent_replay": payload.get("idempotent_replay", False),
        "error_type": payload.get("detail") if response["status"] != 200 else None,
    }


def _json_request(
    url: str,
    api_key: str,
    *,
    method: str,
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": response.status,
                "worker_pid": response.headers.get("X-Agent-Worker-Pid"),
                "payload": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"detail": "invalid_error_response"}
        return {
            "status": exc.code,
            "worker_pid": exc.headers.get("X-Agent-Worker-Pid"),
            "payload": payload,
        }
    except Exception as exc:  # noqa: BLE001 - load harness records transport failure
        return {
            "status": 0,
            "worker_pid": None,
            "payload": {"detail": type(exc).__name__},
        }


def _configured_store() -> ControlPlaneStore:
    database_url = os.getenv("SOFTWARE_AGENT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL is required.")
    return ControlPlaneStore(database_url)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--api-key")
    parser.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if args.prepare:
        report = prepare_candidate(args.candidate_id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not args.api_key:
        parser.error("--api-key is required unless --prepare is used")
    report = run_http_experiment(
        args.base_url,
        args.api_key,
        candidate_id=args.candidate_id,
        requests=args.requests,
        concurrency=args.concurrency,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
