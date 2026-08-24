from __future__ import annotations

from pathlib import Path

import pytest

from app.evidence.validator import EvidenceValidator
from app.rag.retriever import DocumentRetriever
from app.tools.rag_tool import RAGRetrieverTool
from evaluation.rag_eval import run_rag_evaluation


def test_chunks_have_stable_standard_schema():
    chunks = DocumentRetriever(mode="hybrid").chunks

    assert len(chunks) == 6
    assert {chunk.chunk_id for chunk in chunks} == {
        "release_note:release-1213",
        "release_note:release-1214",
        "software_manual:openssl",
        "software_manual:ethtool",
        "software_manual:nginx",
        "software_manual:tcpdump",
    }
    assert all(chunk.document_id and chunk.section and chunk.content for chunk in chunks)


@pytest.mark.parametrize("mode", ["legacy", "bm25", "hybrid"])
def test_retrieval_modes_have_compatible_and_explainable_output(mode):
    results = DocumentRetriever(mode=mode).retrieve("release 1214", top_k=3)

    assert results[0]["chunk_id"] == "release_note:release-1214"
    assert results[0]["retriever_mode"] == mode
    assert {"source", "title", "content", "score", "matched_terms"} <= results[0].keys()
    assert {"legacy", "bm25", "rrf", "reranker", "final"} <= results[0]["scores"].keys()


def test_hybrid_retrieval_supports_chinese_alias_and_is_deterministic():
    retriever = DocumentRetriever(mode="hybrid")
    first = retriever.retrieve("抓包工具", top_k=3)
    second = retriever.retrieve("抓包工具", top_k=3)

    assert first == second
    assert first[0]["chunk_id"] == "software_manual:tcpdump"


def test_source_and_version_filters_are_applied_before_ranking():
    retriever = DocumentRetriever(mode="hybrid")

    manual = retriever.retrieve("packet capture", source_filter="software_manual")
    release = retriever.retrieve("packages", version_filter="1214")

    assert manual and all(item["document_id"] == "software_manual" for item in manual)
    assert [item["chunk_id"] for item in release] == ["release_note:release-1214"]


@pytest.mark.parametrize("query", ["", "mysql database manual", "release 9999 packages"])
def test_empty_and_no_answer_queries_return_no_chunks(query):
    version = "9999" if "9999" in query else None

    assert DocumentRetriever(mode="hybrid").retrieve(query, version_filter=version) == []


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError, match="Unsupported retrieval mode"):
        DocumentRetriever(mode="remote")


def test_rag_tool_uses_chunk_id_for_valid_citations():
    observation = RAGRetrieverTool(mode="hybrid").run("抓包工具")

    assert observation["status"] == "success"
    assert observation["retriever_mode"] == "hybrid"
    assert observation["evidence_items"][0]["source_id"] == "software_manual:tcpdump"
    assert EvidenceValidator().validate_observation(observation)["valid"]


def test_hybrid_rag_evaluation_meets_thresholds_without_legacy_regression():
    report = run_rag_evaluation()

    assert report["passed"]
    assert report["regressed_metrics"] == []
    assert report["modes"]["hybrid"]["recall_at_3"] >= 0.90
    assert report["modes"]["hybrid"]["recall_at_5"] >= 0.95
    assert report["modes"]["hybrid"]["mrr"] >= 0.85
    assert report["modes"]["hybrid"]["citation_correctness"] >= 0.95
    assert report["modes"]["hybrid"]["no_answer_accuracy"] >= 0.90
