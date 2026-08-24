"""Concurrent HTTP load harness for a real multi-worker Agent deployment."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


def _request(base_url: str, api_key: str, index: int, timeout: float) -> dict[str, Any]:
    body = json.dumps(
        {
            "query": "查询openssl依赖",
            "session_id": f"load-{uuid.uuid4().hex}-{index}",
            "persist_trajectory": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/agent/query",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "status": response.status,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "worker_pid": response.headers.get("X-Agent-Worker-Pid"),
                "success": bool(payload.get("success")),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "worker_pid": exc.headers.get("X-Agent-Worker-Pid"),
            "success": False,
        }
    except Exception as exc:  # noqa: BLE001 - load harness records transport failures
        return {
            "status": 0,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "worker_pid": None,
            "success": False,
            "error": type(exc).__name__,
        }


def run_load(
    base_url: str,
    api_key: str,
    *,
    requests: int = 100,
    concurrency: int = 16,
    timeout: float = 20,
) -> dict[str, Any]:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(_request, base_url, api_key, index, timeout)
            for index in range(requests)
        ]
        results = [future.result() for future in as_completed(futures)]
    latencies = sorted(float(item["latency_ms"]) for item in results)
    successes = sum(item["status"] == 200 and item["success"] for item in results)
    server_errors = sum(int(item["status"]) >= 500 for item in results)
    workers = sorted({item["worker_pid"] for item in results if item["worker_pid"]})
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    report = {
        "benchmark": "Software-Agent-Step27-MultiWorker-Load",
        "requests": requests,
        "concurrency": concurrency,
        "successes": successes,
        "success_rate": round(successes / requests, 4) if requests else 0,
        "server_errors": server_errors,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_latency_ms": round(latencies[p95_index], 2) if latencies else None,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "worker_pids": workers,
        "worker_count_observed": len(workers),
        "passed": successes == requests and server_errors == 0 and len(workers) >= 2,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--allow-single-worker", action="store_true")
    args = parser.parse_args()
    report = run_load(
        args.base_url,
        args.api_key,
        requests=args.requests,
        concurrency=args.concurrency,
    )
    if args.allow_single_worker and report["successes"] == report["requests"]:
        report["passed"] = True
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
