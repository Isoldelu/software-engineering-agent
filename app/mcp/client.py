"""Small real-process stdio Client for the Software-Agent MCP Server."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUESTS: tuple[tuple[str, str], ...] = (
    ("package_search", "query openssl version"),
    ("dependency_analysis", "openssl dependencies"),
    ("version_compare", "compare openssl version changes"),
)

_ENV_ALLOWLIST = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "PYTHONHOME",
    "PYTHONPATH",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "VIRTUAL_ENV",
    "WINDIR",
}


def build_stdio_server_parameters(
    *, python_executable: str | None = None
) -> StdioServerParameters:
    """Build a portable subprocess launch without forwarding Provider credentials."""
    environment = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
    inherited_python_path = environment.get("PYTHONPATH", "")
    python_paths = [str(PROJECT_ROOT)]
    if inherited_python_path:
        python_paths.append(inherited_python_path)
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    environment["SOFTWARE_AGENT_ENABLE_ONLINE_LLM"] = "false"
    environment["SOFTWARE_AGENT_LLM_PROVIDER"] = "offline"
    return StdioServerParameters(
        command=python_executable or sys.executable,
        args=["-B", "-m", "app.mcp.server"],
        env=environment,
    )


async def run_stdio_client(
    requests: Sequence[tuple[str, str]] = DEFAULT_REQUESTS,
    *,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Discover and call Tools through a real MCP stdio subprocess."""
    started = time.perf_counter()
    parameters = build_stdio_server_parameters(python_executable=python_executable)
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        initialized = await session.initialize()
        discovery_started = time.perf_counter()
        listed = await session.list_tools()
        discovery_latency_ms = _elapsed_ms(discovery_started)
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in listed.tools
        ]
        calls: list[dict[str, Any]] = []
        for tool_name, query in requests:
            call_started = time.perf_counter()
            result = await session.call_tool(tool_name, arguments={"query": query})
            structured = result.structured_content
            if result.is_error:
                raise RuntimeError(f"MCP Tool {tool_name!r} returned an error.")
            if not isinstance(structured, dict):
                raise TypeError(f"MCP Tool {tool_name!r} did not return structured content.")
            calls.append(
                {
                    "tool": tool_name,
                    "query": query,
                    "latency_ms": _elapsed_ms(call_started),
                    "observation": structured,
                }
            )
    return {
        "transport": "stdio",
        "process_boundary": True,
        "server": {
            "name": initialized.server_info.name,
            "version": initialized.server_info.version,
        },
        "tools": tools,
        "calls": calls,
        "discovery_latency_ms": discovery_latency_ms,
        "total_latency_ms": _elapsed_ms(started),
        "provider_calls": 0,
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
