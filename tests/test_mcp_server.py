from __future__ import annotations

import asyncio

from app.mcp.client import build_stdio_server_parameters, run_stdio_client
from app.mcp.server import mcp_server
from evaluation.mcp_smoke import EXPECTED_TOOLS, run_mcp_smoke


def test_mcp_server_registers_exact_read_only_tool_set():
    tools = asyncio.run(mcp_server.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert all("query" in tool.input_schema.get("required", []) for tool in tools)


def test_stdio_subprocess_discovers_and_calls_all_tools():
    result = asyncio.run(run_stdio_client())

    assert result["transport"] == "stdio"
    assert result["process_boundary"] is True
    assert result["server"]["name"] == "software-agent-tools"
    assert {tool["name"] for tool in result["tools"]} == EXPECTED_TOOLS
    assert [call["observation"]["status"] for call in result["calls"]] == [
        "success",
        "success",
        "success",
    ]
    assert result["provider_calls"] == 0


def test_mcp_subprocess_environment_does_not_forward_provider_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-test-value")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-value")

    parameters = build_stdio_server_parameters()

    assert "DEEPSEEK_API_KEY" not in parameters.env
    assert "OPENAI_API_KEY" not in parameters.env
    assert parameters.env["SOFTWARE_AGENT_ENABLE_ONLINE_LLM"] == "false"
    assert parameters.env["SOFTWARE_AGENT_LLM_PROVIDER"] == "offline"


def test_mcp_smoke_covers_not_found_and_direct_tool_parity():
    report = asyncio.run(run_mcp_smoke())

    assert report["passed"]
    assert report["call_count"] == 4
    assert report["gates"]["success_and_not_found_covered"]
    assert report["gates"]["local_tool_parity"]
    assert report["provider_calls"] == 0
    assert report["secrets_exposed"] is False
