from app.tools.component_tool import ComponentMappingTool
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.version_tool import VersionCompareTool


def test_package_search_tool():
    result = PackageSearchTool().run("openssl")

    assert result["status"] == "success"
    assert result["result"]["version"] == "3.0.8"


def test_dependency_tool():
    result = DependencyAnalysisTool().run("tcpdump dependencies")

    assert result["status"] == "success"
    assert result["dependencies"] == ["libpcap.so"]


def test_version_tool():
    result = VersionCompareTool().run("nginx compare version")

    assert result["status"] == "success"
    assert result["old_version"] == "1.20"
    assert result["new_version"] == "1.24"


def test_component_mapping_tool():
    result = ComponentMappingTool().run("which package owns libssl.so")

    assert result["status"] == "success"
    assert result["owners"][0]["package"] == "openssl"
