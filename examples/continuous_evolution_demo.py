"""Run the deterministic Step 38 continuous Shadow evolution demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.continuous_evolution_eval import (
    run_continuous_evolution_evaluation,
)

if __name__ == "__main__":
    report = run_continuous_evolution_evaluation()
    summary = {
        "benchmark": report["benchmark"],
        "processed_trace_count": report["processed_trace_count"],
        "drift_signals": report["drift_signals"],
        "candidate_count": report["candidate_count"],
        "candidate_statuses": report["candidate_statuses"],
        "fixed_bad_case_count": report["fixed_bad_case_count"],
        "regressed_case_count": report["regressed_case_count"],
        "paid_api_calls": report["paid_api_calls"],
        "passed": report["passed"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
