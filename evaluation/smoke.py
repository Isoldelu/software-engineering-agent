"""Small CI gate covering core Agent behavior and policy rollback."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.control_plane_eval import run_control_plane_evaluation
from evaluation.eval_runner import run_evaluation
from evaluation.policy_eval import run_policy_evaluation
from evaluation.provider_eval import run_provider_evaluation


def run_smoke() -> dict:
    core = run_evaluation()
    policy = run_policy_evaluation()
    provider = run_provider_evaluation()
    control_plane = run_control_plane_evaluation()
    passed = (
        not core["bad_cases"]
        and policy["passed"]
        and provider["passed"]
        and control_plane["passed"]
    )
    return {
        "benchmark": "Software-Agent-CI-Smoke",
        "core_cases": core["total"],
        "core_bad_cases": len(core["bad_cases"]),
        "policy_passed": policy["passed"],
        "provider_passed": provider["passed"],
        "control_plane_passed": control_plane["passed"],
        "passed": passed,
    }


if __name__ == "__main__":
    report = run_smoke()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
