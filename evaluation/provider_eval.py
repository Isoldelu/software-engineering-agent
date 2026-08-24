"""Evaluate offline/online planning parity and failure-safe fallback."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evaluation" / "provider_cases.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.planner import build_plan
from app.providers.gateway import PlannerGateway
from app.providers.mock import MockPlanningProvider
from app.providers.models import ProviderResult
from app.providers.offline import OfflinePlanningProvider
from app.providers.service import run_agent_with_provider
from app.providers.settings import ProviderSettings


def run_provider_evaluation() -> dict[str, Any]:
    queries = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    settings = ProviderSettings(default_provider="offline", online_enabled=True)
    valid_provider = MockPlanningProvider(
        lambda request: ProviderResult(
            provider="mock_online",
            status="success",
            plan_output=_plan_json(request.query),
            model="mock-structured-plan-v1",
            latency_ms=2.0,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )
    )
    gateway = PlannerGateway(
        settings,
        providers={"offline": OfflinePlanningProvider(), "openai": valid_provider},
    )
    comparisons = []
    for query in queries:
        offline = run_agent_with_provider(query, provider="offline", gateway=gateway)
        online = run_agent_with_provider(query, provider="openai", gateway=gateway)
        comparisons.append({
            "query": query,
            "offline_tool": offline["selected_tool"],
            "online_tool": online["selected_tool"],
            "offline_used_tools": offline["used_tools"],
            "online_used_tools": online["used_tools"],
            "same_plan": (
                offline["selected_tool"] == online["selected_tool"]
                and offline["used_tools"] == online["used_tools"]
            ),
            "online_provider": online["provider"]["effective_provider"],
            "online_trace_provider": online["trace"]["provider"]["effective_provider"],
        })

    injected = {
        "malformed_json": ProviderResult(
            provider="mock_online", status="success", plan_output="not-json"
        ),
        "unknown_tool": ProviderResult(
            provider="mock_online",
            status="success",
            plan_output=json.dumps({
                "intent": "unsafe",
                "tool": "shell",
                "arguments": {},
                "steps": [{"tool": "shell", "arguments": {}, "reason": "unsafe"}],
            }),
        ),
        "timeout": ProviderResult(
            provider="mock_online",
            status="error",
            plan_output=None,
            error_type="timeout",
            error_message="injected timeout",
        ),
    }
    fallback_results = {}
    for name, provider_result in injected.items():
        failure_provider = MockPlanningProvider(lambda request, value=provider_result: value)
        failure_gateway = PlannerGateway(
            settings,
            providers={"offline": OfflinePlanningProvider(), "openai": failure_provider},
        )
        result = run_agent_with_provider(
            "openssl 依赖哪些组件",
            provider="openai",
            gateway=failure_gateway,
        )
        fallback_results[name] = {
            "fallback_used": result["provider"]["fallback_used"],
            "effective_provider": result["provider"]["effective_provider"],
            "selected_tool": result["selected_tool"],
            "success": result["success"],
            "fallback_reason": result["provider"].get("fallback_reason"),
        }

    blocked_gateway = PlannerGateway(
        settings,
        providers={
            "offline": OfflinePlanningProvider(),
            "openai": MockPlanningProvider(lambda request: injected["timeout"]),
        },
    )
    blocked = blocked_gateway.plan(
        "openssl 依赖哪些组件", provider="openai", allow_fallback=False
    )
    thresholds = {
        "offline_online_plan_parity": all(item["same_plan"] for item in comparisons),
        "online_metadata_in_trace": all(
            item["online_provider"] == "mock_online"
            and item["online_trace_provider"] == "mock_online"
            for item in comparisons
        ),
        "all_failure_modes_fallback": all(
            item["fallback_used"] and item["effective_provider"] == "offline"
            for item in fallback_results.values()
        ),
        "fallback_execution_success": all(
            item["success"] and item["selected_tool"] == "dependency_analysis"
            for item in fallback_results.values()
        ),
        "fallback_can_be_disabled": blocked.metadata["execution_allowed"] is False,
        "online_call_count_bounded": valid_provider.call_count == len(queries),
    }
    return {
        "benchmark": "Software-Agent-Provider-Dual-Mode",
        "case_count": len(queries),
        "offline_online_plan_parity": sum(item["same_plan"] for item in comparisons) / len(queries),
        "online_mock_calls": valid_provider.call_count,
        "fallback_cases": fallback_results,
        "comparisons": comparisons,
        "thresholds": thresholds,
        "paid_api_calls": 0,
        "passed": all(thresholds.values()),
        "bad_cases": [key for key, value in thresholds.items() if not value],
    }


def _plan_json(query: str) -> str:
    plan = build_plan(query)
    return json.dumps({
        "intent": plan["intent"],
        "tool": plan["tool"],
        "arguments": plan.get("arguments", {}),
        "confidence": plan.get("confidence", "medium"),
        "reason": plan.get("reason", "Mock online structured plan."),
        "steps": plan["steps"],
    }, ensure_ascii=False)


if __name__ == "__main__":
    print(json.dumps(run_provider_evaluation(), ensure_ascii=False, indent=2))
