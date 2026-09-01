"""Deterministic vs JSON Planner vs native Tool Calling paid comparison."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evaluation" / "native_tool_calling_cases.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.providers.deepseek_provider import DeepSeekPlanningProvider
from app.providers.gateway import PlannerGateway
from app.providers.native_tool_provider import DeepSeekNativeToolAgent, NativeToolResult
from app.providers.offline import OfflinePlanningProvider
from app.providers.service import run_agent_with_provider
from app.providers.settings import ProviderSettings

MAX_CASES = 10
MAX_NATIVE_ROUNDS = 3
MAX_PROJECTED_PROVIDER_CALLS = MAX_CASES * (1 + MAX_NATIVE_ROUNDS)
PEAK_INPUT_USD_PER_MILLION = 0.44
PEAK_OUTPUT_USD_PER_MILLION = 1.32


class NativeRunner(Protocol):
    def run(self, query: str) -> NativeToolResult: ...


def run_native_tool_comparison(
    *,
    max_cases: int = MAX_CASES,
    json_gateway: PlannerGateway | None = None,
    native_runner: NativeRunner | None = None,
) -> dict[str, Any]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    selected = cases[: max(1, min(MAX_CASES, int(max_cases)))]
    gateway, native = _real_components(json_gateway, native_runner)
    comparisons: list[dict[str, Any]] = []

    for case in selected:
        query = case["query"]
        required = set(case["required_tools"])
        expected_status = case.get("expected_status", "success")

        deterministic_started = time.perf_counter()
        deterministic = run_agent_with_provider(
            query,
            provider="offline",
            gateway=gateway,
            persist_trajectory=False,
        )
        deterministic_latency = _elapsed_ms(deterministic_started)
        json_plan = run_agent_with_provider(
            query,
            provider="deepseek",
            gateway=gateway,
            persist_trajectory=False,
        )
        native_result = native.run(query)

        json_provider = json_plan["provider"]
        json_failed = json_provider.get("fallback_reason") or {}
        json_tools = json_plan.get("used_tools", [])
        native_tools = native_result.used_tools
        comparisons.append(
            {
                "query": query,
                "required_tools": case["required_tools"],
                "expected_status": expected_status,
                "deterministic": _method_case(
                    used_tools=deterministic.get("used_tools", []),
                    required=required,
                    execution_status=deterministic.get("execution_status"),
                    expected_status=expected_status,
                    valid=True,
                    provider_rounds=0,
                    tool_call_count=deterministic.get("tool_call_count", 0),
                    latency_ms=deterministic_latency,
                    usage={},
                ),
                "json_planner": _method_case(
                    used_tools=json_tools,
                    required=required,
                    execution_status=json_plan.get("execution_status"),
                    expected_status=expected_status,
                    valid=(
                        json_provider.get("effective_provider") == "deepseek"
                        and not json_provider.get("fallback_used")
                    ),
                    provider_rounds=1,
                    tool_call_count=json_plan.get("tool_call_count", 0),
                    latency_ms=float(
                        json_failed.get("latency_ms", json_provider.get("latency_ms", 0.0)) or 0.0
                    ),
                    usage=json_failed.get("usage", json_provider.get("usage", {})),
                    fallback_used=bool(json_provider.get("fallback_used")),
                    error_type=json_failed.get("error_type", json_provider.get("error_type")),
                ),
                "native_tool_calling": _method_case(
                    used_tools=native_tools,
                    required=required,
                    execution_status=native_result.execution_status,
                    expected_status=expected_status,
                    valid=(
                        native_result.status == "success"
                        and native_result.invalid_tool_call_count == 0
                    ),
                    provider_rounds=native_result.provider_rounds,
                    tool_call_count=native_result.tool_call_count,
                    latency_ms=native_result.provider_latency_ms,
                    usage=native_result.usage,
                    invalid_tool_call_count=native_result.invalid_tool_call_count,
                    error_type=native_result.error_type,
                    tool_call_trace=native_result.tool_calls,
                ),
            }
        )

    methods = {
        name: _aggregate_method(comparisons, name)
        for name in ("deterministic", "json_planner", "native_tool_calling")
    }
    actual_provider_calls = int(
        sum(item["json_planner"]["provider_rounds"] for item in comparisons)
        + sum(item["native_tool_calling"]["provider_rounds"] for item in comparisons)
    )
    native_attempts = sum(item["native_tool_calling"]["tool_call_count"] for item in comparisons)
    native_invalid = sum(
        item["native_tool_calling"]["invalid_tool_call_count"] for item in comparisons
    )
    native_validity = (
        (native_attempts - native_invalid) / native_attempts if native_attempts else 0.0
    )
    gates = {
        "case_count_bounded": len(comparisons) <= MAX_CASES,
        "projected_provider_calls_bounded": (
            len(comparisons) * (1 + MAX_NATIVE_ROUNDS) <= MAX_PROJECTED_PROVIDER_CALLS
        ),
        "actual_provider_calls_bounded": actual_provider_calls <= MAX_PROJECTED_PROVIDER_CALLS,
        "native_tool_call_validity_at_least_90_percent": native_validity >= 0.9,
        "native_required_tool_accuracy_at_least_80_percent": (
            methods["native_tool_calling"]["required_tool_accuracy"] >= 0.8
        ),
        "native_run_valid_rate_at_least_90_percent": (
            methods["native_tool_calling"]["valid_rate"] >= 0.9
        ),
        "native_task_success_at_least_90_percent": (
            methods["native_tool_calling"]["task_success_rate"] >= 0.9
        ),
        "report_contains_no_secret_fields": "api_key"
        not in json.dumps({"methods": methods, "comparisons": comparisons}).lower(),
    }
    return {
        "benchmark": "Software-Agent-DeepSeek-Native-Tool-Calling-AB",
        "model": gateway.settings.deepseek_model,
        "thinking_mode": "disabled",
        "case_count": len(comparisons),
        "max_native_rounds_per_case": MAX_NATIVE_ROUNDS,
        "max_projected_provider_calls": MAX_PROJECTED_PROVIDER_CALLS,
        "actual_provider_calls": actual_provider_calls,
        "native_tool_call_validity": native_validity,
        "methods": methods,
        "comparisons": comparisons,
        "cost_assumption": {
            "method": "conservative peak cache-miss upper bound",
            "input_usd_per_million_tokens": PEAK_INPUT_USD_PER_MILLION,
            "output_usd_per_million_tokens": PEAK_OUTPUT_USD_PER_MILLION,
            "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
        },
        "gates": gates,
        "passed": all(gates.values()),
        "bad_cases": [name for name, passed in gates.items() if not passed],
        "case_failures": [
            {
                "query": item["query"],
                "methods": [
                    name
                    for name in ("deterministic", "json_planner", "native_tool_calling")
                    if not item[name]["task_success"]
                ],
            }
            for item in comparisons
            if any(
                not item[name]["task_success"]
                for name in ("deterministic", "json_planner", "native_tool_calling")
            )
        ],
        "secrets_exposed": False,
    }


def _method_case(
    *,
    used_tools: list[str],
    required: set[str],
    execution_status: str | None,
    expected_status: str,
    valid: bool,
    provider_rounds: int,
    tool_call_count: int,
    latency_ms: float,
    usage: dict[str, int],
    fallback_used: bool = False,
    invalid_tool_call_count: int = 0,
    error_type: str | None = None,
    tool_call_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    required_covered = required.issubset(used_tools)
    return {
        "used_tools": used_tools,
        "valid": valid,
        "required_tools_covered": required_covered,
        "execution_status": execution_status,
        "task_success": bool(valid and required_covered and execution_status == expected_status),
        "provider_rounds": provider_rounds,
        "tool_call_count": tool_call_count,
        "latency_ms": round(latency_ms, 3),
        "usage": usage,
        "fallback_used": fallback_used,
        "invalid_tool_call_count": invalid_tool_call_count,
        "error_type": error_type,
        "tool_call_trace": tool_call_trace or [],
    }


def _aggregate_method(comparisons: list[dict[str, Any]], name: str) -> dict[str, Any]:
    items = [comparison[name] for comparison in comparisons]
    count = len(items)
    input_tokens = sum(item["usage"].get("input_tokens", 0) for item in items)
    output_tokens = sum(item["usage"].get("output_tokens", 0) for item in items)
    total_tokens = sum(item["usage"].get("total_tokens", 0) for item in items)
    latencies = [float(item["latency_ms"]) for item in items]
    estimated_cost = (
        input_tokens / 1_000_000 * PEAK_INPUT_USD_PER_MILLION
        + output_tokens / 1_000_000 * PEAK_OUTPUT_USD_PER_MILLION
    )
    return {
        "valid_rate": sum(item["valid"] for item in items) / count,
        "required_tool_accuracy": (sum(item["required_tools_covered"] for item in items) / count),
        "task_success_rate": sum(item["task_success"] for item in items) / count,
        "fallback_rate": sum(item["fallback_used"] for item in items) / count,
        "average_provider_rounds": round(sum(item["provider_rounds"] for item in items) / count, 3),
        "average_tool_calls": round(sum(item["tool_call_count"] for item in items) / count, 3),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_peak_cost_upper_bound_usd": round(estimated_cost, 8),
    }


def _real_components(
    json_gateway: PlannerGateway | None,
    native_runner: NativeRunner | None,
) -> tuple[PlannerGateway, NativeRunner]:
    if json_gateway is not None and native_runner is not None:
        return json_gateway, native_runner
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError(
            "A rotated DEEPSEEK_API_KEY is required for the real Step 36 experiment."
        )
    settings = replace(
        ProviderSettings.from_env(),
        default_provider="deepseek",
        online_enabled=True,
        native_max_rounds=MAX_NATIVE_ROUNDS,
    )
    gateway = json_gateway or PlannerGateway(
        settings,
        providers={
            "offline": OfflinePlanningProvider(),
            "deepseek": DeepSeekPlanningProvider(settings),
        },
    )
    return gateway, native_runner or DeepSeekNativeToolAgent(settings)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return round(ordered[index], 3)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=MAX_CASES)
    parser.add_argument("--confirm-paid-calls", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.confirm_paid_calls:
        parser.error("--confirm-paid-calls is required for real network requests")
    if not 1 <= args.max_cases <= MAX_CASES:
        parser.error(f"--max-cases must be within 1..{MAX_CASES}")

    report = run_native_tool_comparison(max_cases=args.max_cases)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
