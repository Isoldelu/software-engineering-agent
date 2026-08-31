from __future__ import annotations

import json
from types import SimpleNamespace
from typing import ClassVar

from app.agent.planner import build_plan
from app.providers.gateway import PlannerGateway
from app.providers.mock import MockPlanningProvider
from app.providers.models import ProviderResult
from app.providers.native_tool_provider import (
    DeepSeekNativeToolAgent,
    NativeToolResult,
    _validate_tool_call,
)
from app.providers.offline import OfflinePlanningProvider
from app.providers.settings import ProviderSettings
from evaluation.native_tool_calling_eval import run_native_tool_comparison


def _tool_call(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(
    *,
    tool_calls: list[SimpleNamespace] | None = None,
    content: str | None = None,
    finish_reason: str = "tool_calls",
    input_tokens: int = 100,
    output_tokens: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


class SequenceCompletions:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_native_tool_loop_executes_allowlisted_calls_and_accumulates_rounds():
    completions = SequenceCompletions(
        [
            _response(
                tool_calls=[
                    _tool_call(
                        "call-dep",
                        "dependency_analysis",
                        json.dumps({"query": "openssl dependencies"}),
                    ),
                    _tool_call(
                        "call-version",
                        "version_compare",
                        json.dumps({"query": "compare openssl version changes"}),
                    ),
                ]
            ),
            _response(
                content="OpenSSL dependency and version evidence was found.",
                finish_reason="stop",
                input_tokens=180,
                output_tokens=30,
            ),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = DeepSeekNativeToolAgent(ProviderSettings(online_enabled=True), client=client)

    result = agent.run("查一下 openssl 的版本变化和依赖")

    assert result.status == "success"
    assert result.execution_status == "success"
    assert result.provider_rounds == 2
    assert result.tool_call_count == 2
    assert result.invalid_tool_call_count == 0
    assert result.used_tools == ["dependency_analysis", "version_compare"]
    assert result.usage == {
        "input_tokens": 280,
        "output_tokens": 50,
        "total_tokens": 330,
    }
    assert completions.requests[0]["tool_choice"] == "required"
    assert completions.requests[1]["tool_choice"] == "auto"
    assert len(completions.requests[0]["tools"]) == 5
    assert completions.requests[0]["extra_body"]["thinking"] == {"type": "disabled"}
    second_messages = completions.requests[1]["messages"]
    assert [message["role"] for message in second_messages[-3:]] == [
        "assistant",
        "tool",
        "tool",
    ]


def test_native_tool_loop_blocks_unknown_tool_without_execution():
    completions = SequenceCompletions(
        [
            _response(tool_calls=[_tool_call("call-shell", "shell", '{"query":"whoami"}')]),
            _response(content="The tool request was blocked.", finish_reason="stop"),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = DeepSeekNativeToolAgent(ProviderSettings(online_enabled=True), client=client).run(
        "run shell"
    )

    assert result.status == "error"
    assert result.execution_status == "failed"
    assert result.tool_call_count == 1
    assert result.valid_tool_call_count == 0
    assert result.invalid_tool_call_count == 1
    assert result.tool_calls[0]["error_type"] == "unknown_tool"
    assert json.loads(completions.requests[1]["messages"][-1]["content"]) == {
        "status": "blocked",
        "error": "unknown_tool",
    }


def test_native_tool_argument_validator_rejects_invalid_and_extra_arguments():
    assert _validate_tool_call("package_search", "not-json")[0] == ("arguments_invalid_json")
    assert _validate_tool_call("package_search", "[]")[0] == ("arguments_must_be_object")
    assert (
        _validate_tool_call("package_search", '{"query":"openssl","command":"dir"}')[0]
        == "arguments_schema_mismatch"
    )
    assert _validate_tool_call("package_search", '{"query":""}')[0] == (
        "query_must_be_non_empty_string"
    )


def test_native_provider_error_redacts_process_key(monkeypatch):
    secret = "private-native-test-value"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)

    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError(f"request rejected for key {secret}")

    client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))
    result = DeepSeekNativeToolAgent(ProviderSettings(online_enabled=True), client=client).run(
        "query openssl"
    )

    assert result.status == "error"
    assert result.error_type == "RuntimeError"
    assert secret not in (result.error_message or "")
    assert "[redacted]" in (result.error_message or "")


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


class StubNativeRunner:
    TOOLS: ClassVar[dict[str, list[str]]] = {
        "查询 openssl 的软件版本": ["package_search"],
        "openssl 依赖哪些组件": ["dependency_analysis"],
        "比较 openssl 两个版本变化": ["version_compare"],
    }

    def run(self, query: str) -> NativeToolResult:
        tools = self.TOOLS[query]
        return NativeToolResult(
            provider="deepseek_native_tools",
            model="deepseek-v4-flash-test",
            status="success",
            execution_status="success",
            final_answer="grounded answer",
            provider_rounds=2,
            tool_call_count=len(tools),
            valid_tool_call_count=len(tools),
            invalid_tool_call_count=0,
            used_tools=tools,
            usage={"input_tokens": 200, "output_tokens": 40, "total_tokens": 240},
            provider_latency_ms=25.0,
            total_latency_ms=28.0,
        )


def test_three_way_comparison_runs_with_injected_providers_without_network():
    settings = ProviderSettings(online_enabled=True, default_provider="deepseek")
    json_provider = MockPlanningProvider(
        lambda request: ProviderResult(
            provider="deepseek",
            status="success",
            plan_output=_plan_json(request.query),
            model="deepseek-v4-flash-test",
            latency_ms=10.0,
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
    )
    gateway = PlannerGateway(
        settings,
        providers={"offline": OfflinePlanningProvider(), "deepseek": json_provider},
    )

    report = run_native_tool_comparison(
        max_cases=3,
        json_gateway=gateway,
        native_runner=StubNativeRunner(),
    )

    assert report["passed"]
    assert report["case_count"] == 3
    assert report["actual_provider_calls"] == 9
    assert report["native_tool_call_validity"] == 1.0
    assert report["methods"]["deterministic"]["task_success_rate"] == 1.0
    assert report["methods"]["json_planner"]["task_success_rate"] == 1.0
    assert report["methods"]["native_tool_calling"]["task_success_rate"] == 1.0
    assert report["methods"]["native_tool_calling"]["average_provider_rounds"] == 2
    assert report["methods"]["native_tool_calling"]["total_tokens"] == 720
    assert report["secrets_exposed"] is False
