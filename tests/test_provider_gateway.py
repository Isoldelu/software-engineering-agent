from __future__ import annotations

import json
from types import SimpleNamespace

from app.agent.planner import build_plan
from app.providers.gateway import PlannerGateway
from app.providers.mock import MockPlanningProvider
from app.providers.models import ProviderResult
from app.providers.offline import OfflinePlanningProvider
from app.providers.openai_provider import OpenAIPlanningProvider
from app.providers.service import run_agent_with_provider
from app.providers.settings import ProviderSettings
from evaluation.provider_eval import run_provider_evaluation


def _valid_plan(query="openssl 依赖哪些组件"):
    plan = build_plan(query)
    return json.dumps({
        "intent": plan["intent"],
        "tool": plan["tool"],
        "arguments": plan["arguments"],
        "confidence": plan["confidence"],
        "reason": plan["reason"],
        "steps": plan["steps"],
    }, ensure_ascii=False)


def _gateway(result):
    return PlannerGateway(
        ProviderSettings(online_enabled=True),
        providers={
            "offline": OfflinePlanningProvider(),
            "openai": MockPlanningProvider(lambda request: result),
        },
    )


def test_default_settings_are_offline_and_online_is_opt_in(monkeypatch):
    for name in (
        "SOFTWARE_AGENT_LLM_PROVIDER",
        "SOFTWARE_AGENT_ENABLE_ONLINE_LLM",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = ProviderSettings.from_env()

    assert settings.default_provider == "offline"
    assert settings.online_enabled is False
    assert settings.public_status()["openai_api_key_configured"] is False


def test_invalid_numeric_environment_settings_fall_back_to_bounded_defaults(monkeypatch):
    monkeypatch.setenv("SOFTWARE_AGENT_LLM_TIMEOUT", "invalid")
    monkeypatch.setenv("SOFTWARE_AGENT_LLM_MAX_OUTPUT_TOKENS", "999999")

    settings = ProviderSettings.from_env()

    assert settings.timeout_seconds == 20.0
    assert settings.max_output_tokens == 2000


def test_valid_mock_online_plan_runs_existing_tool_chain_and_enters_trace():
    gateway = _gateway(ProviderResult(
        provider="mock_online",
        status="success",
        plan_output=_valid_plan(),
        model="mock-v1",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    ))
    result = run_agent_with_provider(
        "openssl 依赖哪些组件", provider="openai", gateway=gateway
    )

    assert result["selected_tool"] == "dependency_analysis"
    assert result["provider"]["effective_provider"] == "mock_online"
    assert result["provider"]["usage"]["total_tokens"] == 15
    assert result["trace"]["provider"]["effective_provider"] == "mock_online"


def test_invalid_json_unknown_tool_and_timeout_fall_back_offline():
    results = [
        ProviderResult(provider="mock_online", status="success", plan_output="bad"),
        ProviderResult(
            provider="mock_online",
            status="success",
            plan_output=json.dumps({
                "intent": "bad", "tool": "shell", "arguments": {},
                "steps": [{"tool": "shell", "arguments": {}, "reason": "bad"}],
            }),
        ),
        ProviderResult(
            provider="mock_online", status="error", plan_output=None,
            error_type="timeout", error_message="timeout",
        ),
    ]
    for provider_result in results:
        result = run_agent_with_provider(
            "openssl 依赖哪些组件",
            provider="openai",
            gateway=_gateway(provider_result),
        )
        assert result["provider"]["fallback_used"] is True
        assert result["provider"]["effective_provider"] == "offline"
        assert result["selected_tool"] == "dependency_analysis"


def test_fallback_retains_redacted_failed_provider_metrics():
    result = run_agent_with_provider(
        "openssl 依赖哪些组件",
        provider="openai",
        gateway=_gateway(
            ProviderResult(
                provider="mock_online",
                status="error",
                plan_output=None,
                model="mock-v1",
                latency_ms=12.5,
                usage={"input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
                error_type="invalid_plan",
                error_message="schema rejected",
            )
        ),
    )

    failed = result["provider"]["fallback_reason"]
    assert failed["model"] == "mock-v1"
    assert failed["latency_ms"] == 12.5
    assert failed["usage"]["total_tokens"] == 24


def test_provider_failure_can_fail_closed_when_fallback_disabled():
    decision = _gateway(ProviderResult(
        provider="mock_online", status="error", plan_output=None, error_type="timeout"
    )).plan("query", provider="openai", allow_fallback=False)

    assert decision.plan_output is None
    assert decision.metadata["execution_allowed"] is False
    assert decision.metadata["fallback_used"] is False


def test_openai_adapter_requests_strict_schema_and_captures_usage(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-sent")
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=_valid_plan(),
                usage=SimpleNamespace(input_tokens=20, output_tokens=8, total_tokens=28),
            )

    provider = OpenAIPlanningProvider(
        ProviderSettings(online_enabled=True, openai_model="gpt-5-mini"),
        client=SimpleNamespace(responses=Responses()),
    )
    result = provider.generate_plan(SimpleNamespace(
        prompt="prompt", timeout_seconds=3, max_output_tokens=200, query="query"
    ))

    assert result.status == "success"
    assert result.usage["total_tokens"] == 28
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True


def test_status_never_exposes_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    status = PlannerGateway(ProviderSettings()).status()

    assert status["settings"]["openai_api_key_configured"] is True
    assert "secret-value" not in json.dumps(status)
    assert status["secrets_exposed"] is False


def test_provider_evaluation_passes_without_paid_calls():
    report = run_provider_evaluation()

    assert report["passed"]
    assert report["offline_online_plan_parity"] == 1.0
    assert report["paid_api_calls"] == 0
    assert report["bad_cases"] == []
