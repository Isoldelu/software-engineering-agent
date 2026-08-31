from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent.planner import build_plan
from app.providers.deepseek_provider import DeepSeekPlanningProvider
from app.providers.gateway import PlannerGateway
from app.providers.mock import MockPlanningProvider
from app.providers.models import ProviderResult
from app.providers.offline import OfflinePlanningProvider
from app.providers.settings import ProviderSettings
from evaluation.real_provider_eval import run_real_provider_evaluation


def _plan_json(query: str) -> str:
    plan = build_plan(query)
    return json.dumps(
        {
            "intent": plan["intent"],
            "tool": plan["tool"],
            "arguments": plan.get("arguments", {}),
            "confidence": plan.get("confidence", "medium"),
            "reason": plan.get("reason", "test"),
            "steps": plan["steps"],
        },
        ensure_ascii=False,
    )


def test_deepseek_adapter_requests_json_non_thinking_and_captures_usage(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-sent")
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                model="deepseek-v4-flash",
                choices=[SimpleNamespace(message=SimpleNamespace(content=_plan_json("query")))],
                usage=SimpleNamespace(
                    prompt_tokens=120,
                    completion_tokens=30,
                    total_tokens=150,
                ),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    provider = DeepSeekPlanningProvider(
        ProviderSettings(online_enabled=True),
        client=client,
    )
    result = provider.generate_plan(
        SimpleNamespace(prompt="JSON planner prompt", timeout_seconds=3, max_output_tokens=400)
    )

    assert result.status == "success"
    assert result.usage["total_tokens"] == 150
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["extra_body"]["thinking"] == {"type": "disabled"}
    assert captured["max_tokens"] == 400
    assert "JSON" in captured["messages"][0]["content"]


def test_planner_prompt_requires_object_arguments_and_minimal_tool_selection():
    from app.agent.prompt import build_planner_prompt

    prompt = build_planner_prompt("查询 openssl 的软件版本")

    assert '"arguments": {' in prompt
    assert "Use exactly one step for a single intent" in prompt
    assert "Use hybrid_plan only" in prompt
    assert "Do not add speculative tools" in prompt


def test_deepseek_settings_and_status_never_expose_key(monkeypatch):
    monkeypatch.setenv("SOFTWARE_AGENT_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("SOFTWARE_AGENT_ENABLE_ONLINE_LLM", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-test-value")
    settings = ProviderSettings.from_env()
    status = PlannerGateway(settings).status()

    assert settings.default_provider == "deepseek"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert status["providers"]["deepseek"]["available"] is True
    assert status["settings"]["deepseek_api_key_configured"] is True
    assert "private-test-value" not in json.dumps(status)


def test_real_provider_evaluation_can_run_with_injected_provider_without_network():
    settings = ProviderSettings(online_enabled=True, default_provider="deepseek")
    provider = MockPlanningProvider(
        lambda request: ProviderResult(
            provider="deepseek",
            status="success",
            plan_output=_plan_json(request.query),
            model="deepseek-v4-flash-test",
            latency_ms=12.5,
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
    )
    gateway = PlannerGateway(
        settings,
        providers={"offline": OfflinePlanningProvider(), "deepseek": provider},
    )

    report = run_real_provider_evaluation(max_calls=3, gateway=gateway)

    assert report["passed"]
    assert report["case_count"] == 3
    assert report["metrics"]["structured_plan_valid_rate"] == 1.0
    assert report["metrics"]["required_tool_accuracy"] == 1.0
    assert report["metrics"]["exact_plan_parity_vs_deterministic"] == 1.0
    assert report["metrics"]["total_tokens"] == 360
    assert report["secrets_exposed"] is False
