from __future__ import annotations

import pytest

from app.tools.component_tool import ComponentMappingTool
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.rag_tool import RAGRetrieverTool
from app.tools.version_tool import VersionCompareTool


SUCCESS_CASES = [
    (PackageSearchTool, "query openssl version", {"result_type", "result"}),
    (DependencyAnalysisTool, "tcpdump dependencies", {"package", "dependencies"}),
    (VersionCompareTool, "compare nginx version", {"old_version", "new_version", "changes"}),
    (ComponentMappingTool, "which package owns libssl.so", {"component", "owners"}),
    (RAGRetrieverTool, "release note says what was added in 1214", {"results", "message"}),
]

NOT_FOUND_CASES = [
    (PackageSearchTool, "query package metadata for nonexistent"),
    (DependencyAnalysisTool, "nonexistent dependencies"),
    (VersionCompareTool, "compare nonexistent version"),
    (ComponentMappingTool, "which package owns missing.so"),
    (RAGRetrieverTool, "release note for release 9999"),
]


@pytest.mark.parametrize(("tool_class", "query", "business_fields"), SUCCESS_CASES)
def test_tool_success_contract(tool_class, query, business_fields):
    result = tool_class().run(query)

    assert result["tool"] == tool_class.name
    assert result["status"] == "success"
    assert result["query"] == query
    assert "evidence" in result
    assert business_fields <= result.keys()


@pytest.mark.parametrize(("tool_class", "query"), NOT_FOUND_CASES)
def test_tool_not_found_contract(tool_class, query):
    result = tool_class().run(query)

    assert result["tool"] == tool_class.name
    assert result["status"] == "not_found"
    assert result["query"] == query
    assert isinstance(result.get("message"), str)
    assert result["message"]
    assert "evidence" in result


def test_dependency_empty_list_is_success_not_missing_data():
    result = DependencyAnalysisTool().run("ethtool dependencies")

    assert result["status"] == "success"
    assert result["dependencies"] == []
