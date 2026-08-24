"""Freeze and verify the Step 17 behavioral compatibility baseline."""

from __future__ import annotations

import argparse
import difflib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "evaluation" / "baseline-v1.json"
GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "agent_outputs.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.workflow import run_agent
from app.api.schemas import AgentQueryResponse
from app.tools.component_tool import ComponentMappingTool
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.rag_tool import RAGRetrieverTool
from app.tools.version_tool import VersionCompareTool
from evaluation.eval_runner import (
    run_bad_case_analysis,
    run_benchmark_experiment,
    run_evaluation,
    run_large_benchmark,
    run_robustness_evaluation,
)


GOLDEN_QUERIES = [
    "query openssl version",
    "1214 release packages and their dependencies",
    "query package metadata for nonexistent",
]

TOOL_CASES = [
    (PackageSearchTool, "query openssl version"),
    (DependencyAnalysisTool, "tcpdump dependencies"),
    (VersionCompareTool, "compare nginx version"),
    (ComponentMappingTool, "which package owns libssl.so"),
    (RAGRetrieverTool, "release note says what was added in 1214"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write or verify the Software-Agent Step 17 compatibility baseline."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write baseline-v1.json and the Workflow golden fixture.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Compare current behavior with baseline-v1.json (default).",
    )
    args = parser.parse_args()

    if args.write:
        write_baseline()
        return
    check_baseline()


def write_baseline() -> None:
    """Persist the current deterministic behavior as baseline v1."""
    golden_cases = build_golden_cases()
    snapshot = build_snapshot(golden_cases=golden_cases)
    document = {
        "metadata": {
            "baseline_version": "baseline-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "evaluation_case_count": snapshot["evaluation"]["total_cases"],
            "write_command": "python -B evaluation/baseline.py --write",
            "check_command": "python -B evaluation/baseline.py --check",
        },
        "snapshot": snapshot,
    }
    _write_json(BASELINE_PATH, document)
    _write_json(
        GOLDEN_PATH,
        {
            "schema_version": "workflow-golden-v1",
            "cases": golden_cases,
        },
    )
    print(f"Wrote compatibility baseline: {BASELINE_PATH}")
    print(f"Wrote Workflow golden fixture: {GOLDEN_PATH}")
    print(f"Evaluation cases frozen: {snapshot['evaluation']['total_cases']}")


def check_baseline() -> None:
    """Fail when current deterministic behavior differs from baseline v1."""
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Baseline does not exist: {BASELINE_PATH}. Run with --write first."
        )

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = build_snapshot()
    expected = baseline["snapshot"]
    if is_compatible(expected, current):
        print(
            "Baseline check passed: "
            f"{current['evaluation']['total_cases']} evaluation cases are compatible."
        )
        return

    expected_text = _canonical_json(expected).splitlines()
    current_text = _canonical_json(current).splitlines()
    difference = list(
        difflib.unified_diff(
            expected_text,
            current_text,
            fromfile="baseline-v1",
            tofile="current",
            lineterm="",
        )
    )
    preview = "\n".join(difference[:200])
    raise SystemExit(f"Baseline check failed. Behavioral differences detected:\n{preview}")


def is_compatible(expected: Any, current: Any, path: tuple[str, ...] = ()) -> bool:
    """Allow additive V2 fields while requiring every V1 value to remain unchanged."""
    if isinstance(expected, dict):
        if not isinstance(current, dict):
            return False
        return all(
            key in current and is_compatible(value, current[key], path + (key,))
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(current, list):
            return False
        if path and path[-1] in {
            "agent_query_response_fields",
            "success_output_fields",
        }:
            return all(item in current for item in expected)
        return len(expected) == len(current) and all(
            is_compatible(expected_item, current_item, path + (str(index),))
            for index, (expected_item, current_item) in enumerate(zip(expected, current))
        )
    return expected == current


def build_snapshot(golden_cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the stable behavioral payload compared by baseline checks."""
    golden_cases = golden_cases or build_golden_cases()
    reports = {
        "benchmark": run_evaluation(),
        "challenge": run_bad_case_analysis(),
        "robustness": run_robustness_evaluation(),
        "large": run_large_benchmark(),
    }
    experiment = run_benchmark_experiment()["summary"]
    total_cases = sum(report["total"] for report in reports.values())

    agent_fields = getattr(AgentQueryResponse, "model_fields", None)
    if agent_fields is None:
        agent_fields = AgentQueryResponse.__fields__

    return _normalize({
        "schema_version": "compatibility-snapshot-v1",
        "api_contract": {
            "health": {
                "status": "ok",
                "service": "ai-software-engineering-agent",
            },
            "agent_query_response_fields": sorted(agent_fields.keys()),
            "representative_response": golden_cases[0]["result"],
        },
        "tool_contract": {
            tool_class.name: {
                "success_output_fields": sorted(tool_class().run(query).keys())
            }
            for tool_class, query in TOOL_CASES
        },
        "workflow_golden": golden_cases,
        "evaluation": {
            "total_cases": total_cases,
            "suites": {
                name: _evaluation_payload(report)
                for name, report in reports.items()
            },
            "experiment_summary": experiment,
        },
    })


def build_golden_cases() -> list[dict[str, Any]]:
    """Capture representative single-tool, Hybrid, and not-found workflows."""
    return [
        {
            "query": query,
            "result": _normalize(run_agent(query, persist_trajectory=False)),
        }
        for query in GOLDEN_QUERIES
    ]


def _evaluation_payload(report: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "benchmark",
        "total",
        "tool_routing_accuracy",
        "task_success_rate",
        "answer_grounding_accuracy",
        "answer_accuracy",
        "average_tool_calls",
        "bad_cases",
        "results",
    ]
    return {field: report[field] for field in fields}


def _normalize(value: Any) -> Any:
    """Replace workspace-specific paths while preserving behavioral values."""
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        normalized_root = str(PROJECT_ROOT).replace("\\", "/")
        return value.replace("\\", "/").replace(normalized_root, "<PROJECT_ROOT>")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
