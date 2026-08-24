from app.agent.workflow import run_agent


def test_package_search_agent():
    result = run_agent("query openssl version", persist_trajectory=False)

    assert result["success"] is True
    assert result["selected_tool"] == "package_search"
    assert "openssl" in result["answer"]
    assert "3.0.8" in result["answer"]


def test_hybrid_agent_plan():
    result = run_agent("1214 release packages and their dependencies", persist_trajectory=False)

    assert result["success"] is True
    assert result["selected_tool"] == "hybrid_plan"
    assert result["used_tools"] == [
        "rag_retrieval",
        "package_search",
        "dependency_analysis",
        "dependency_analysis",
    ]
    assert "nginx" in result["answer"]
    assert "libpcap.so" in result["answer"]
