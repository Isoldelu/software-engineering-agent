"""Run the deterministic 20% rollout and automatic rollback demonstration."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.policy_eval import run_policy_evaluation


if __name__ == "__main__":
    print(json.dumps(run_policy_evaluation(), ensure_ascii=False, indent=2))
