"""Read-only MCP Server exposing selected deterministic Agent Tools."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.version_tool import VersionCompareTool

mcp_server = MCPServer(
    "software-agent-tools",
    title="Software-Agent Deterministic Tools",
    description="Read-only software asset lookup over simulated local data.",
    instructions=(
        "Use these tools only for package metadata, dependency analysis, and version changes. "
        "Every response is derived from the simulated Software-Agent dataset."
    ),
    version="1.0.0",
    log_level="WARNING",
)

_package_tool = PackageSearchTool()
_dependency_tool = DependencyAnalysisTool()
_version_tool = VersionCompareTool()


@mcp_server.tool()
def package_search(query: str) -> dict[str, Any]:
    """Search package version, release, architecture, and file metadata."""
    return _package_tool.run(query)


@mcp_server.tool()
def dependency_analysis(query: str) -> dict[str, Any]:
    """Analyze direct or reverse package dependencies."""
    return _dependency_tool.run(query)


@mcp_server.tool()
def version_compare(query: str) -> dict[str, Any]:
    """Compare recorded package versions and summarize changes."""
    return _version_tool.run(query)


def main() -> None:
    """Run the local MCP Server over stdio."""
    mcp_server.run("stdio")


if __name__ == "__main__":
    main()
