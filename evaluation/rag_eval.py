"""Evaluate legacy, BM25, and Hybrid retrieval on labeled document chunks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_CASES_PATH = PROJECT_ROOT / "evaluation" / "rag_cases.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evidence.normalizer import citations_from_evidence
from app.evidence.validator import EvidenceValidator
from app.rag.retriever import DocumentRetriever
from app.tools.rag_tool import RAGRetrieverTool


def run_rag_evaluation(cases_path: Path = RAG_CASES_PATH) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    mode_reports = {
        mode: _evaluate_mode(cases, mode)
        for mode in ("legacy", "bm25", "hybrid")
    }
    hybrid = mode_reports["hybrid"]
    legacy = mode_reports["legacy"]
    regressions = [
        metric
        for metric in ("recall_at_3", "recall_at_5", "mrr", "no_answer_accuracy")
        if hybrid[metric] < legacy[metric]
    ]
    thresholds = {
        "recall_at_3": hybrid["recall_at_3"] >= 0.90,
        "recall_at_5": hybrid["recall_at_5"] >= 0.95,
        "mrr": hybrid["mrr"] >= 0.85,
        "citation_correctness": hybrid["citation_correctness"] >= 0.95,
        "no_answer_accuracy": hybrid["no_answer_accuracy"] >= 0.90,
        "no_regression_vs_legacy": not regressions,
    }
    return {
        "benchmark": "Software-Agent-Hybrid-RAG",
        "total": len(cases),
        "modes": mode_reports,
        "hybrid_thresholds": thresholds,
        "regressed_metrics": regressions,
        "passed": all(thresholds.values()),
    }


def _evaluate_mode(cases: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    retriever = DocumentRetriever(mode=mode)
    results = []
    for case in cases:
        retrieved = retriever.retrieve(
            case["query"],
            top_k=5,
            source_filter=case.get("source_filter"),
            version_filter=case.get("version_filter"),
        )
        retrieved_ids = [item["chunk_id"] for item in retrieved]
        relevant = set(case.get("relevant_chunk_ids", []))
        reciprocal_rank = 0.0
        for rank, chunk_id in enumerate(retrieved_ids, start=1):
            if chunk_id in relevant:
                reciprocal_rank = 1.0 / rank
                break
        no_answer_correct = not case.get("no_answer") or not retrieved_ids
        results.append({
            "id": case["id"],
            "query": case["query"],
            "relevant_chunk_ids": sorted(relevant),
            "retrieved_chunk_ids": retrieved_ids,
            "recall_at_3": bool(relevant & set(retrieved_ids[:3])) if relevant else True,
            "recall_at_5": bool(relevant & set(retrieved_ids[:5])) if relevant else True,
            "reciprocal_rank": reciprocal_rank if relevant else 1.0,
            "no_answer_correct": no_answer_correct,
        })

    answerable = [item for item in results if item["relevant_chunk_ids"]]
    no_answer = [
        item for item, case in zip(results, cases)
        if case.get("no_answer")
    ]
    citation_correctness = _citation_correctness(cases, mode)
    return {
        "mode": mode,
        "answerable_cases": len(answerable),
        "no_answer_cases": len(no_answer),
        "recall_at_3": _mean(answerable, "recall_at_3"),
        "recall_at_5": _mean(answerable, "recall_at_5"),
        "mrr": _mean(answerable, "reciprocal_rank"),
        "no_answer_accuracy": _mean(no_answer, "no_answer_correct"),
        "citation_correctness": citation_correctness,
        "bad_cases": [
            item for item in results
            if not item["recall_at_5"] or not item["no_answer_correct"]
        ],
        "results": results,
    }


def _citation_correctness(cases: list[dict[str, Any]], mode: str) -> float:
    validations = []
    tool = RAGRetrieverTool(mode=mode)
    validator = EvidenceValidator()
    for case in cases:
        if case.get("no_answer") or case.get("source_filter"):
            continue
        observation = tool.run(case["query"])
        evidence = observation.get("evidence_items", [])
        citations = citations_from_evidence(evidence)
        validations.append(validator.validate(evidence, citations)["valid"])
    return sum(validations) / len(validations) if validations else 1.0


def _mean(items: list[dict[str, Any]], key: str) -> float:
    return sum(float(item[key]) for item in items) / len(items) if items else 1.0


if __name__ == "__main__":
    print(json.dumps(run_rag_evaluation(), ensure_ascii=False, indent=2))
