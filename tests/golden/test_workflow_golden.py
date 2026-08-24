from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.workflow import run_agent
from evaluation.baseline import _normalize, is_compatible


GOLDEN_PATH = Path(__file__).with_name("agent_outputs.json")


def _load_cases() -> list[dict]:
    document = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert document["schema_version"] == "workflow-golden-v1"
    return document["cases"]


@pytest.mark.parametrize("case", _load_cases() if GOLDEN_PATH.exists() else [])
def test_workflow_matches_golden_output(case):
    current = _normalize(run_agent(case["query"], persist_trajectory=False))

    assert is_compatible(case["result"], current)


def test_golden_fixture_contains_required_workflow_types():
    cases = _load_cases()
    results = [case["result"] for case in cases]

    assert len(cases) == 3
    assert any(result["selected_tool"] == "package_search" for result in results)
    assert any(result["selected_tool"] == "hybrid_plan" for result in results)
    assert any(result["success"] is False for result in results)
