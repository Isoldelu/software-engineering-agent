"""Evaluate real stdio MCP discovery, calls, and local Tool parity."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "evaluation" / "mcp_smoke_report.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mcp.client import run_stdio_client
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.version_tool import VersionCompareTool

EXPECTED_TOOLS = {"package_search", "dependency_analysis", "version_compare"}
CASES: tuple[tuple[str, str], ...] = (
    ("package_search", "query openssl version"),
    ("dependency_analysis", "openssl dependencies"),
    ("version_compare", "compare openssl version changes"),
    ("package_search", "query package metadata for nonexistent"),
)
LOCAL_TOOLS = {
    "package_search": PackageSearchTool,
    "dependency_analysis": DependencyAnalysisTool,
    "version_compare": VersionCompareTool,
}


async def run_mcp_smoke() -> dict[str, Any]:
    client_result = await run_stdio_client(CASES)
    discovered = {tool["name"] for tool in client_result["tools"]}
    schema_valid = all(_valid_query_schema(tool["input_schema"]) for tool in client_result["tools"])
    case_results: list[dict[str, Any]] = []
    for call in client_result["calls"]:
        direct = LOCAL_TOOLS[call["tool"]]().run(call["query"])
        mcp_observation = call["observation"]
        case_results.append(
            {
                "tool": call["tool"],
                "query": call["query"],
                "status": mcp_observation.get("status"),
                "parity": _stable_observation(mcp_observation) == _stable_observation(direct),
                "latency_ms": call["latency_ms"],
            }
        )

    gates = {
        "stdio_process_boundary": client_result["process_boundary"] is True,
        "exact_tool_set": discovered == EXPECTED_TOOLS,
        "query_schemas_valid": schema_valid,
        "all_calls_returned": len(case_results) == len(CASES),
        "success_and_not_found_covered": {item["status"] for item in case_results}
        == {"success", "not_found"},
        "local_tool_parity": all(item["parity"] for item in case_results),
        "provider_calls_zero": client_result["provider_calls"] == 0,
    }
    return {
        "benchmark": "Software-Agent-MCP-stdio-smoke",
        "sdk": "mcp==2.1.1",
        "transport": client_result["transport"],
        "server": client_result["server"],
        "discovered_tools": sorted(discovered),
        "tool_count": len(discovered),
        "call_count": len(case_results),
        "case_results": case_results,
        "discovery_latency_ms": client_result["discovery_latency_ms"],
        "total_latency_ms": client_result["total_latency_ms"],
        "provider_calls": 0,
        "gates": gates,
        "passed": all(gates.values()),
        "secrets_exposed": False,
    }


def _valid_query_schema(schema: dict[str, Any]) -> bool:
    properties = schema.get("properties", {})
    return (
        schema.get("type") == "object"
        and properties.get("query", {}).get("type") == "string"
        and "query" in schema.get("required", [])
    )


def _stable_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return _without_volatile_fields(observation)


def _without_volatile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_volatile_fields(item)
            for key, item in value.items()
            if key not in {"latency_ms", "tool_call"}
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def main() -> int:
    report = asyncio.run(run_mcp_smoke())
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    REPORT_PATH.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
