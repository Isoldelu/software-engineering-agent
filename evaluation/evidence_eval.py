"""Evaluate Evidence normalization and Citation coverage across all 193 cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATHS = [
    PROJECT_ROOT / "evaluation" / "test_cases.json",
    PROJECT_ROOT / "evaluation" / "challenge_cases.json",
    PROJECT_ROOT / "evaluation" / "robustness_cases.json",
    PROJECT_ROOT / "evaluation" / "large_benchmark.json",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.workflow import run_agent
from app.evidence.validator import EvidenceValidator


def run_evidence_evaluation() -> dict[str, Any]:
    """Return Evidence/Citation metrics without changing the 193-case benchmark."""
    cases = [
        case
        for path in CASE_PATHS
        for case in json.loads(path.read_text(encoding="utf-8"))
    ]
    results = [_evaluate_case(case) for case in cases]

    observation_count = sum(item["observation_count"] for item in results)
    normalized_count = sum(item["normalized_observation_count"] for item in results)
    citation_required = sum(1 for item in results if item["citation_required"])
    citation_covered = sum(
        1 for item in results
        if item["citation_required"] and item["citation_covered"]
    )
    citation_valid = sum(1 for item in results if item["citations_valid"])
    not_found_cases = [item for item in results if item["expected_status"] == "not_found"]
    unsupported_facts = sum(len(item["unsupported_facts"]) for item in results)

    return {
        "benchmark": "Software-Agent-Evidence",
        "total": len(results),
        "citation_coverage": _ratio(citation_covered, citation_required),
        "evidence_normalization_success": _ratio(normalized_count, observation_count),
        "citation_correctness": _ratio(citation_valid, len(results)),
        "not_found_without_citation": _ratio(
            sum(1 for item in not_found_cases if item["not_found_without_citation"]),
            len(not_found_cases),
        ),
        "unsupported_structured_facts": unsupported_facts,
        "bad_case_count": sum(1 for item in results if item["issues"]),
        "bad_cases": [item for item in results if item["issues"]],
        "results": results,
    }


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    result = run_agent(case["query"], persist_trajectory=False)
    tool_observations = [
        item["observation"]
        for item in result.get("trajectory", [])
        if item.get("stage") == "tool_execution"
    ]
    validator = EvidenceValidator()
    observation_validations = [
        validator.validate_observation(observation)
        for observation in tool_observations
    ]
    citation_validation = validator.validate(
        result.get("evidence_items", []),
        result.get("citations", []),
    )
    expected_status = case.get("expected_status", "success")
    citation_required = any(
        observation.get("status") == "success" for observation in tool_observations
    )
    citation_covered = not citation_required or bool(result.get("citations"))
    not_found_without_citation = (
        not result.get("evidence_items") and not result.get("citations")
    ) if expected_status == "not_found" else True
    unsupported_facts = _unsupported_facts(
        case.get("expected_answer_contains", []),
        result.get("evidence_items", []),
        expected_status,
    )

    issues = [
        issue
        for validation in observation_validations
        for issue in validation["issues"]
    ]
    issues.extend(citation_validation["issues"])
    if not citation_covered:
        issues.append({
            "type": "missing_citation",
            "message": "A successful answer did not expose a Citation.",
        })
    if not not_found_without_citation:
        issues.append({
            "type": "not_found_has_citation",
            "message": "A not_found task exposed unsupported Evidence or Citation.",
        })
    if unsupported_facts:
        issues.append({
            "type": "unsupported_expected_fact",
            "message": f"Expected facts were not found in Evidence: {unsupported_facts}",
        })

    return {
        "query": case["query"],
        "expected_status": expected_status,
        "observation_count": len(tool_observations),
        "normalized_observation_count": sum(
            1 for validation in observation_validations if validation["valid"]
        ),
        "evidence_count": result.get("evidence_count", 0),
        "citation_count": len(result.get("citations", [])),
        "citation_required": citation_required,
        "citation_covered": citation_covered,
        "citations_valid": citation_validation["valid"],
        "not_found_without_citation": not_found_without_citation,
        "unsupported_facts": unsupported_facts,
        "issues": issues,
    }


def _unsupported_facts(
    expected_fragments: list[str],
    evidence_items: list[dict[str, Any]],
    expected_status: str,
) -> list[str]:
    if expected_status == "not_found":
        return []
    evidence_text = json.dumps(evidence_items, ensure_ascii=False).lower()
    return [
        fragment for fragment in expected_fragments
        if fragment.lower() not in evidence_text
    ]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


if __name__ == "__main__":
    print(json.dumps(run_evidence_evaluation(), ensure_ascii=False, indent=2))
