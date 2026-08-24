from __future__ import annotations

from app.agent.workflow import run_agent
from app.api.schemas import AgentQueryResponse
from app.api.schemas import AgentQueryRequest
from app.api.schemas import AgentProviderQueryRequest


AGENT_RESPONSE_FIELDS = {
    "query",
    "intent",
    "selected_tool",
    "answer",
    "used_tools",
    "tool_call_count",
    "evidence",
    "confidence",
    "success",
    "plan",
    "trajectory",
}


def test_agent_query_response_fields_remain_available():
    result = run_agent("query openssl version", persist_trajectory=False)

    assert AGENT_RESPONSE_FIELDS <= result.keys()
    AgentQueryResponse(**result)


def test_agent_query_endpoint_preserves_response_semantics_when_fastapi_is_available():
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from app.api.server import agent_query

    result = agent_query(
        AgentQueryRequest(query="query openssl version", persist_trajectory=False)
    )

    assert AGENT_RESPONSE_FIELDS <= result.keys()
    assert result["selected_tool"] == "package_search"
    assert result["success"] is True
    assert result["tool_call_count"] == len(result["used_tools"])


def test_health_contract():
    from app.api.schemas import HealthResponse

    response = HealthResponse(
        status="ok",
        service="ai-software-engineering-agent",
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    assert payload == {
        "status": "ok",
        "service": "ai-software-engineering-agent",
    }


def test_provider_endpoint_defaults_to_zero_cost_offline_mode():
    from app.api.server import agent_query_provider, provider_status

    result = agent_query_provider(AgentProviderQueryRequest(
        query="openssl 依赖哪些组件",
        provider="offline",
        persist_trajectory=False,
    ))
    status = provider_status()

    assert result["selected_tool"] == "dependency_analysis"
    assert result["provider"]["effective_provider"] == "offline"
    assert result["provider"]["usage"]["total_tokens"] == 0
    assert status["secrets_exposed"] is False


def test_provider_endpoint_fails_closed_when_online_is_unavailable_and_fallback_disabled(
    monkeypatch,
):
    pytest = __import__("pytest")
    from fastapi import HTTPException
    from app.providers.gateway import PlannerGateway
    from app.providers.settings import ProviderSettings
    import app.providers.service as provider_service
    from app.api.server import agent_query_provider

    monkeypatch.setattr(
        provider_service,
        "DEFAULT_PLANNER_GATEWAY",
        PlannerGateway(ProviderSettings(default_provider="offline", online_enabled=False)),
    )

    with pytest.raises(HTTPException) as raised:
        agent_query_provider(AgentProviderQueryRequest(
            query="openssl 依赖哪些组件",
            provider="openai",
            allow_fallback=False,
            persist_trajectory=False,
        ))

    assert raised.value.status_code == 503
    assert raised.value.detail["provider"]["execution_allowed"] is False
