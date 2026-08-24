from __future__ import annotations

import json

from app.agent.verifier import CHECKED_RULES, aggregate_execution_status
from app.agent.workflow import run_agent
from app.api.schemas import AgentQueryResponse
from evaluation.verifier_eval import PARTIAL_PLAN, run_verifier_evaluation


def test_verifier_has_at_least_eight_deterministic_rules():
    assert len(CHECKED_RULES) >= 8
    assert len(CHECKED_RULES) == len(set(CHECKED_RULES))


def test_valid_answer_passes_online_verification():
    result = run_agent("query openssl version", persist_trajectory=False)

    assert result["execution_status"] == "success"
    assert result["verification"]["passed"] is True
    assert result["verification"]["issues"] == []
    assert result["verification"]["repair_count"] == 0


def test_partial_success_is_exposed_without_changing_legacy_success_boolean():
    result = run_agent(
        "partial success verifier demo",
        persist_trajectory=False,
        llm_plan_output=json.dumps(PARTIAL_PLAN),
    )

    assert result["execution_status"] == "partial_success"
    assert result["success"] is False
    assert result["verification"]["passed"] is True
    assert "Missing records" in result["answer"]


def test_execution_status_aggregation():
    scenarios = [
        (["success"], "success"),
        (["success", "not_found"], "partial_success"),
        (["not_found", "not_found"], "not_found"),
        (["success", "failed"], "failed"),
        (["partial_success", "success"], "partial_success"),
    ]
    for statuses, expected in scenarios:
        observations = [
            {"observation": {"status": status}} for status in statuses
        ]
        assert aggregate_execution_status(observations) == expected


def test_api_schema_exposes_verification_and_execution_status():
    result = run_agent("query openssl version", persist_trajectory=False)
    response = AgentQueryResponse(**result)
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    assert payload["execution_status"] == "success"
    assert payload["verification"]["passed"] is True


def test_verifier_evaluation_meets_step_19_targets():
    report = run_verifier_evaluation()

    assert report["injected_error_detection"] >= 0.95
    assert report["false_rejection_rate"] <= 0.05
    assert report["partial_success_classification"] >= 0.95
    assert report["invalid_citation_detection"] == 1.0
    assert report["single_repair_passed"] is True
    assert report["max_repair_count"] == 1
    assert report["bad_case_count"] == 0
