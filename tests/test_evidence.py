from __future__ import annotations

from app.agent.workflow import run_agent
from app.evidence.models import Evidence
from app.evidence.validator import EvidenceValidator
from app.api.schemas import AgentQueryResponse
from app.tools.component_tool import ComponentMappingTool
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.rag_tool import RAGRetrieverTool
from app.tools.version_tool import VersionCompareTool
from evaluation.evidence_eval import run_evidence_evaluation


SUCCESS_CASES = [
    (PackageSearchTool, "openssl"),
    (DependencyAnalysisTool, "tcpdump dependencies"),
    (VersionCompareTool, "compare nginx version"),
    (ComponentMappingTool, "which package owns libssl.so"),
    (RAGRetrieverTool, "release note says what was added in 1214"),
]

NOT_FOUND_CASES = [
    (PackageSearchTool, "package nonexistent"),
    (DependencyAnalysisTool, "nonexistent dependencies"),
    (VersionCompareTool, "compare nonexistent version"),
    (ComponentMappingTool, "which package owns missing.so"),
    (RAGRetrieverTool, "release note for 9999"),
]


def test_evidence_id_is_stable_for_the_same_source_fact():
    arguments = {
        "source_type": "package_record",
        "source_id": "packages.json#package=openssl",
        "title": "Package openssl",
        "content": '{"package":"openssl"}',
        "tool_name": "package_search",
    }

    assert Evidence.create(**arguments).evidence_id == Evidence.create(**arguments).evidence_id


def test_tool_repeated_execution_keeps_the_same_evidence_id():
    first = PackageSearchTool().run("openssl")
    second = PackageSearchTool().run("openssl")

    assert first["evidence_items"][0]["evidence_id"] == second["evidence_items"][0]["evidence_id"]


def test_all_tools_produce_normalized_evidence():
    validator = EvidenceValidator()

    for tool_class, query in SUCCESS_CASES:
        result = tool_class().run(query)
        assert result["status"] == "success"
        assert result["evidence_items"]
        assert result["metadata"]["evidence_count"] == len(result["evidence_items"])
        assert validator.validate_observation(result)["valid"] is True


def test_not_found_does_not_fabricate_evidence():
    validator = EvidenceValidator()

    for tool_class, query in NOT_FOUND_CASES:
        result = tool_class().run(query)
        assert result["status"] == "not_found"
        assert result["evidence_items"] == []
        assert validator.validate_observation(result)["valid"] is True


def test_hybrid_plan_merges_unique_evidence_and_valid_citations():
    result = run_agent(
        "1214 release packages and their dependencies",
        persist_trajectory=False,
    )
    evidence_ids = [item["evidence_id"] for item in result["evidence_items"]]

    assert result["success"] is True
    assert result["evidence_count"] == len(evidence_ids)
    assert len(evidence_ids) == len(set(evidence_ids))
    assert {item["evidence_id"] for item in result["citations"]} == set(evidence_ids)
    assert EvidenceValidator().validate(
        result["evidence_items"], result["citations"]
    )["valid"] is True


def test_not_found_agent_has_no_structured_evidence_or_citations():
    result = run_agent("which package owns legacycrypto.so", persist_trajectory=False)

    assert result["success"] is False
    assert result["evidence_items"] == []
    assert result["citations"] == []
    assert result["evidence_count"] == 0


def test_agent_api_schema_exposes_step_18_fields():
    result = run_agent("query openssl version", persist_trajectory=False)
    response = AgentQueryResponse(**result)
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    assert payload["evidence_items"]
    assert payload["citations"]
    assert payload["evidence_count"] == len(payload["evidence_items"])


def test_evidence_evaluation_meets_step_18_targets():
    report = run_evidence_evaluation()

    assert report["total"] == 193
    assert report["citation_coverage"] >= 0.95
    assert report["evidence_normalization_success"] == 1.0
    assert report["citation_correctness"] >= 0.95
    assert report["not_found_without_citation"] == 1.0
    assert report["unsupported_structured_facts"] == 0
