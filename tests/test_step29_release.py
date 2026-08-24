from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_open_source_governance_files_are_present():
    required = (
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        "docs/public-release-audit.md",
    )

    assert all((ROOT / path).is_file() for path in required)
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_v1_release_evidence_matches_verified_ci_results():
    evidence = json.loads(
        (ROOT / "release" / "v1.0.0-evidence.json").read_text(encoding="utf-8")
    )

    assert evidence["release"] == "v1.0.0"
    assert evidence["github_actions"]["run_id"] == 32738626804
    assert set(evidence["github_actions"]["jobs"].values()) == {"success"}
    assert evidence["quality"]["automated_tests"] == 124
    assert evidence["quality"]["frozen_evaluation_cases"] == 193
    assert evidence["postgresql_load"]["initial"]["success_rate"] == 1.0
    assert evidence["postgresql_load"]["after_worker_replacement"]["server_errors"] == 0
    assert evidence["recovery"] == {
        "database_down_ready_status": 503,
        "database_recovered_ready_status": 200,
        "backup_records_restored": 2,
    }
    assert not any(evidence["privacy"].values())


def test_release_files_and_runtime_outputs_have_separate_paths():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "release/" not in ignore
    assert "artifacts/" in ignore
    assert "data/audit/" in ignore
    assert "data/trajectories.jsonl" in ignore
    assert "v1.0.0-evidence.json" in readme
    assert "127.0.0.1:8000/demo" in readme
