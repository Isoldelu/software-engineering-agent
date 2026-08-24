from __future__ import annotations

from pathlib import Path

from app.api.server import app


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_and_development_dependencies_are_separated():
    runtime = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
    development = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "fastapi" in runtime
    assert "uvicorn" in runtime
    assert "pytest" not in runtime
    assert "-r requirements-runtime.txt" in development
    assert all(tool in development for tool in ("pytest", "ruff", "mypy", "httpx"))


def test_container_runs_api_and_has_healthcheck():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "requirements-runtime.txt" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "app.api.server:app" in dockerfile
    assert '"8000:8000"' in compose
    assert "./data:/app/data" in compose


def test_ci_has_required_delivery_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pytest" in workflow
    assert "ruff check --no-cache" in workflow
    assert "mypy" in workflow
    assert "evaluation/smoke.py" in workflow
    assert "docker build" in workflow


def test_policy_release_and_evaluation_routes_are_exposed():
    routes = {(route.path, next(iter(route.methods))) for route in app.routes if route.methods}
    paths = {path for path, _ in routes}

    assert "/policies" in paths
    assert "/policies/from-candidate/{candidate_id}" in paths
    assert "/policies/{policy_id}/rollout" in paths
    assert "/policies/{policy_id}/rollback" in paths
    assert "/policies/{policy_id}/monitor" in paths
    assert "/evaluation/policy" in paths


def test_policy_state_path_can_be_externalized():
    repository_source = (ROOT / "app" / "policy" / "repository.py").read_text(
        encoding="utf-8"
    )

    assert "SOFTWARE_AGENT_POLICY_STATE_PATH" in repository_source
