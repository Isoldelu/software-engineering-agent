from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_demo_module():
    path = ROOT / "examples" / "interview_demo.py"
    spec = importlib.util.spec_from_file_location("interview_demo", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_step30_delivery_files_cover_showcase_demo_and_interview():
    required = (
        "docs/project-showcase.md",
        "docs/demo-runbook.md",
        "docs/interview_talking_points.md",
        "docs/assets/agent-demo.png",
        "docs/assets/evaluation-dashboard.png",
        "examples/interview_demo.py",
    )
    assert all((ROOT / path).is_file() for path in required)

    showcase = (ROOT / "docs" / "project-showcase.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "demo-runbook.md").read_text(encoding="utf-8")
    assert "33309988987" in showcase
    assert "193/193" in showcase
    assert "simulated" in showcase.lower()
    assert "2-3 Minute" in runbook
    assert "--skip-evaluation" in runbook


def test_interview_demo_compacts_agent_trace_and_evaluation_outputs():
    demo = _load_demo_module()
    agent = demo.compact_agent_result({
        "query": "query",
        "execution_status": "success",
        "used_tools": ["package_search", "dependency_analysis"],
        "tool_call_count": 2,
        "evidence_count": 3,
        "citations": [{}, {}],
        "verification": {"passed": True},
        "trace_id": "trace-1",
        "answer": "answer",
    })
    trace = demo.compact_trace({
        "trace": {
            "trace_schema_version": "trace-v1",
            "trace_id": "trace-1",
            "policy_version": "policy-v1",
            "steps": [{}, {}],
            "metrics": {"trace_complete": True, "total_latency_ms": 12.5},
        }
    })
    evaluation = demo.compact_evaluation({
        "summary": {
            "suite_count": 4,
            "total_cases": 193,
            "total_bad_cases": 0,
            "all_suites_passed": True,
        },
        "experiment": {
            "agent_task_success": 1.0,
            "tool_accuracy_improvement": 0.3824,
        },
    })

    assert agent["citation_count"] == 2
    assert agent["verification_passed"] is True
    assert trace["step_count"] == 2
    assert trace["trace_complete"] is True
    assert evaluation["total_cases"] == 193
    assert evaluation["routing_improvement"] == 0.3824


def test_fastapi_release_version_matches_v1_tag():
    server = (ROOT / "app" / "api" / "server.py").read_text(encoding="utf-8")
    demo = (ROOT / "app" / "api" / "demo.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "app" / "api" / "evaluation_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert 'version="1.0.0"' in server
    assert "trace_summary" in demo
    assert "trajectory: data.trajectory" not in demo
    assert "evidence: data.evidence" not in demo
    assert "overflow-x: auto" in dashboard
