"""Small-budget real DeepSeek Planner A/B with explicit paid-call consent."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evaluation" / "real_provider_cases.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.providers.deepseek_provider import DeepSeekPlanningProvider
from app.providers.gateway import PlannerGateway
from app.providers.offline import OfflinePlanningProvider
from app.providers.service import run_agent_with_provider
from app.providers.settings import ProviderSettings

MAX_REAL_CALLS = 20
PEAK_INPUT_USD_PER_MILLION = 0.44
PEAK_OUTPUT_USD_PER_MILLION = 1.32


def run_real_provider_evaluation(
    *,
    max_calls: int = MAX_REAL_CALLS,
    gateway: PlannerGateway | None = None,
) -> dict[str, Any]:
    queries = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    bounded_calls = max(1, min(MAX_REAL_CALLS, int(max_calls)))
    selected = queries[:bounded_calls]
    planner_gateway = gateway or _real_gateway()
    comparisons: list[dict[str, Any]] = []

    for case in selected:
        query = case["query"]
        required_tools = case["required_tools"]
        expected_status = case.get("expected_status", "success")
        offline = run_agent_with_provider(query, provider="offline", gateway=planner_gateway)
        online = run_agent_with_provider(query, provider="deepseek", gateway=planner_gateway)
        provider = online["provider"]
        failed_attempt = provider.get("fallback_reason") or {}
        online_plan_used = (
            provider["effective_provider"] == "deepseek"
            and not provider["fallback_used"]
        )
        same_tools = offline["used_tools"] == online.get("used_tools", [])
        required_tools_covered = set(required_tools).issubset(online.get("used_tools", []))
        comparisons.append(
            {
                "query": query,
                "required_tools": required_tools,
                "expected_status": expected_status,
                "execution_status": online.get("execution_status"),
                "deterministic_tools": offline["used_tools"],
                "deepseek_tools": online.get("used_tools", []),
                "structured_plan_valid": online_plan_used,
                "same_tools": same_tools,
                "required_tools_covered": required_tools_covered,
                "task_success": bool(
                    online_plan_used
                    and required_tools_covered
                    and online.get("execution_status") == expected_status
                ),
                "fallback_used": provider["fallback_used"],
                "fallback_error_type": (
                    failed_attempt.get("error_type")
                ),
                "latency_ms": failed_attempt.get(
                    "latency_ms", provider.get("latency_ms", 0.0)
                ),
                "usage": failed_attempt.get("usage", provider.get("usage", {})),
                "model": failed_attempt.get("model", provider.get("model")),
            }
        )

    input_tokens = sum(item["usage"].get("input_tokens", 0) for item in comparisons)
    output_tokens = sum(item["usage"].get("output_tokens", 0) for item in comparisons)
    total_tokens = sum(item["usage"].get("total_tokens", 0) for item in comparisons)
    latencies = [
        float(item["latency_ms"])
        for item in comparisons
        if item["structured_plan_valid"]
    ]
    valid_count = sum(item["structured_plan_valid"] for item in comparisons)
    same_tool_count = sum(item["same_tools"] for item in comparisons)
    required_tool_count = sum(item["required_tools_covered"] for item in comparisons)
    task_success_count = sum(item["task_success"] for item in comparisons)
    fallback_count = sum(item["fallback_used"] for item in comparisons)
    case_count = len(comparisons)
    estimated_upper_cost = (
        input_tokens / 1_000_000 * PEAK_INPUT_USD_PER_MILLION
        + output_tokens / 1_000_000 * PEAK_OUTPUT_USD_PER_MILLION
    )
    metrics = {
        "structured_plan_valid_rate": valid_count / case_count,
        "required_tool_accuracy": required_tool_count / case_count,
        "exact_plan_parity_vs_deterministic": same_tool_count / case_count,
        "task_success_rate": task_success_count / case_count,
        "fallback_rate": fallback_count / case_count,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_peak_cost_upper_bound_usd": round(estimated_upper_cost, 8),
    }
    gates = {
        "real_calls_bounded": case_count <= MAX_REAL_CALLS,
        "structured_plan_valid_rate_at_least_80_percent": (
            metrics["structured_plan_valid_rate"] >= 0.8
        ),
        "required_tool_accuracy_at_least_80_percent": (
            metrics["required_tool_accuracy"] >= 0.8
        ),
        "task_success_at_least_80_percent": metrics["task_success_rate"] >= 0.8,
        "report_contains_no_secret_fields": "api_key" not in json.dumps(
            {"metrics": metrics, "comparisons": comparisons}
        ).lower(),
    }
    return {
        "benchmark": "Software-Agent-Real-DeepSeek-Provider-AB",
        "provider": "deepseek",
        "model": planner_gateway.settings.deepseek_model,
        "thinking_mode": "disabled",
        "case_count": case_count,
        "metrics": metrics,
        "cost_assumption": {
            "method": "conservative peak cache-miss upper bound",
            "input_usd_per_million_tokens": PEAK_INPUT_USD_PER_MILLION,
            "output_usd_per_million_tokens": PEAK_OUTPUT_USD_PER_MILLION,
            "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
        },
        "comparisons": comparisons,
        "gates": gates,
        "passed": all(gates.values()),
        "bad_cases": [name for name, passed in gates.items() if not passed],
        "secrets_exposed": False,
    }


def _real_gateway() -> PlannerGateway:
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is required for real Provider evaluation.")
    settings = replace(
        ProviderSettings.from_env(),
        default_provider="deepseek",
        online_enabled=True,
    )
    return PlannerGateway(
        settings,
        providers={
            "offline": OfflinePlanningProvider(),
            "deepseek": DeepSeekPlanningProvider(settings),
        },
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=MAX_REAL_CALLS)
    parser.add_argument("--confirm-paid-calls", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.confirm_paid_calls:
        parser.error("--confirm-paid-calls is required for real network requests")
    if not 1 <= args.max_calls <= MAX_REAL_CALLS:
        parser.error(f"--max-calls must be within 1..{MAX_REAL_CALLS}")

    report = run_real_provider_evaluation(max_calls=args.max_calls)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
