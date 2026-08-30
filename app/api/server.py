"""FastAPI server for the AI Software Engineering Agent."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.requests import Request

from app.agent.context import DEFAULT_SESSION_REPOSITORY
from app.agent.llm_router import build_function_specs
from app.agent.prompt import export_tool_schemas
from app.agent.trace import DEFAULT_TRACE_REPOSITORY, ReplayReader
from app.agent.workflow import replay_trace, run_agent
from app.api.demo import DEMO_HTML
from app.api.evaluation_dashboard import EVALUATION_DASHBOARD_HTML
from app.api.schemas import (
    AgentProviderQueryRequest,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentQueryWithPlanRequest,
    ApiKeyRotateRequest,
    CandidateProposeRequest,
    CandidateReviewRequest,
    EvaluationResponse,
    EvolutionReviewRequest,
    FeedbackSubmitRequest,
    HealthResponse,
    PolicyMonitorSampleRequest,
    PolicyReleaseRequest,
    PolicyRollbackRequest,
    PolicyRolloutRequest,
    RetentionRunRequest,
    ToolListResponse,
)
from app.evolution.service import DEFAULT_EVOLUTION_SERVICE
from app.feedback.service import DEFAULT_FEEDBACK_LOOP
from app.maintenance.retention import RetentionService
from app.observability.metrics import DEFAULT_METRICS
from app.policy.service import DEFAULT_POLICY_RELEASE_SERVICE
from app.providers.gateway import DEFAULT_PLANNER_GATEWAY
from app.providers.service import run_agent_with_provider
from app.security.api_key import (
    API_KEY_HEADER,
    ApiKeyAuthenticator,
    AuthConfigurationError,
    AuthenticationError,
    AuthorizationError,
    AuthSettings,
    required_role,
)
from app.security.audit import AuditRepository
from app.security.key_registry import KeyRegistry
from app.storage.database import (
    DEFAULT_CONTROL_PLANE_STORE,
    ConcurrentUpdateError,
    LeaseUnavailableError,
    storage_status,
)
from evaluation.eval_runner import (
    run_bad_case_analysis,
    run_benchmark_experiment,
    run_context_evaluation,
    run_control_plane_evaluation,
    run_evaluation,
    run_evaluation_summary,
    run_evidence_evaluation,
    run_evolution_evaluation,
    run_feedback_loop_evaluation,
    run_policy_evaluation,
    run_provider_evaluation,
    run_rag_evaluation,
    run_robustness_evaluation,
    run_verifier_evaluation,
)


@asynccontextmanager
async def application_lifespan(_app: FastAPI):
    """Release process-owned database resources during Worker shutdown."""
    try:
        yield
    finally:
        if DEFAULT_CONTROL_PLANE_STORE:
            DEFAULT_CONTROL_PLANE_STORE.close()


app = FastAPI(
    title="AI Software Engineering Agent",
    description="A demo Agent service for package analysis, dependency reasoning, RAG, and hybrid tool planning.",
    version="1.0.0",
    lifespan=application_lifespan,
)

DEFAULT_KEY_REGISTRY = (
    KeyRegistry(DEFAULT_CONTROL_PLANE_STORE) if DEFAULT_CONTROL_PLANE_STORE else None
)
DEFAULT_AUDIT_REPOSITORY = (
    AuditRepository(DEFAULT_CONTROL_PLANE_STORE) if DEFAULT_CONTROL_PLANE_STORE else None
)
DEFAULT_RETENTION_SERVICE = (
    RetentionService(DEFAULT_CONTROL_PLANE_STORE) if DEFAULT_CONTROL_PLANE_STORE else None
)


def _record_audit(**event) -> None:
    if not DEFAULT_AUDIT_REPOSITORY:
        return
    try:
        DEFAULT_AUDIT_REPOSITORY.record(**event)
    except Exception:  # noqa: BLE001 - audit is best effort during database failure
        return


@app.middleware("http")
async def api_key_authentication(request: Request, call_next):
    """Apply role-aware API Key checks without changing default local behavior."""
    started = time.perf_counter()
    role = required_role(request.method, request.url.path)
    if role is None:
        response = await call_next(request)
        _observe_http(request, response.status_code, started)
        return response
    provided_key = request.headers.get(API_KEY_HEADER)
    fallback_fingerprint = (
        hashlib.sha256(provided_key.encode("utf-8")).hexdigest()[:12]
        if provided_key
        else None
    )
    try:
        principal = ApiKeyAuthenticator().authenticate(
            provided_key,
            required_role=role,
        )
    except AuthenticationError as exc:
        DEFAULT_METRICS.observe_auth_denial("authentication")
        _record_audit(
            event_type="authentication",
            resource=request.url.path,
            action=request.method,
            outcome="denied",
            actor_fingerprint=fallback_fingerprint,
            details={"status_code": 401, "reason": type(exc).__name__},
        )
        response = JSONResponse(status_code=401, content={"detail": str(exc)})
        _observe_http(request, response.status_code, started)
        return response
    except AuthorizationError as exc:
        DEFAULT_METRICS.observe_auth_denial("authorization")
        _record_audit(
            event_type="authorization",
            resource=request.url.path,
            action=request.method,
            outcome="denied",
            actor_fingerprint=fallback_fingerprint,
            details={"status_code": 403, "reason": type(exc).__name__},
        )
        response = JSONResponse(status_code=403, content={"detail": str(exc)})
        _observe_http(request, response.status_code, started)
        return response
    except AuthConfigurationError as exc:
        DEFAULT_METRICS.observe_auth_denial("configuration")
        response = JSONResponse(status_code=503, content={"detail": str(exc)})
        _observe_http(request, response.status_code, started)
        return response
    request.state.auth_principal = principal.to_dict()
    response = await call_next(request)
    response.headers["X-Agent-Worker-Pid"] = str(os.getpid())
    _record_audit(
        event_type="api_request",
        resource=request.url.path,
        action=request.method,
        outcome="success" if response.status_code < 400 else "failed",
        actor_fingerprint=principal.key_fingerprint,
        actor_role=principal.role,
        details={"status_code": response.status_code},
    )
    _observe_http(request, response.status_code, started)
    return response


def _observe_http(request: Request, status_code: int, started: float) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", "/unmatched-protected-route")
    DEFAULT_METRICS.observe_request(
        request.method,
        route_path,
        status_code,
        time.perf_counter() - started,
    )


@app.exception_handler(ConcurrentUpdateError)
async def concurrent_update_error(_request: Request, exc: ConcurrentUpdateError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(LeaseUnavailableError)
async def lease_unavailable_error(_request: Request, exc: LeaseUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    """Return a small browser demo for the Agent service."""
    return HTMLResponse(DEMO_HTML)


@app.get("/evaluation-dashboard", response_class=HTMLResponse)
def evaluation_dashboard() -> HTMLResponse:
    """Return a browser dashboard for evaluation metrics."""
    return HTMLResponse(EVALUATION_DASHBOARD_HTML)


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    """Return service health."""
    return {
        "status": "ok",
        "service": "ai-software-engineering-agent"
    }


@app.get("/ready")
def readiness() -> dict:
    """Return readiness only when the configured shared database is reachable."""
    status = storage_status(DEFAULT_CONTROL_PLANE_STORE)
    if not status["healthy"]:
        raise HTTPException(status_code=503, detail="Control-plane database is unavailable.")
    return {"status": "ready", "storage": status}


@app.get("/auth/status")
def auth_status() -> dict:
    """Return public authentication configuration without exposing API Keys."""
    status = AuthSettings.from_env().public_status()
    status["database_managed_roles"] = (
        sorted(DEFAULT_KEY_REGISTRY.managed_roles()) if DEFAULT_KEY_REGISTRY else []
    )
    return status


@app.get("/auth/keys")
def auth_key_list() -> dict:
    """List redacted database-managed API Keys."""
    if not DEFAULT_KEY_REGISTRY:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    return {"keys": [item.to_public_dict() for item in DEFAULT_KEY_REGISTRY.list(include_expired=True)]}


@app.post("/auth/keys/rotate")
def auth_key_rotate(request: ApiKeyRotateRequest, http_request: Request) -> dict:
    """Rotate a role Key and return the new secret exactly once."""
    if not DEFAULT_KEY_REGISTRY:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    principal = getattr(http_request.state, "auth_principal", {})
    result = DEFAULT_KEY_REGISTRY.rotate(
        request.role,
        actor=principal.get("key_fingerprint", "unknown"),
        grace_seconds=request.grace_seconds,
        ttl_seconds=request.ttl_seconds,
    )
    _record_audit(
        event_type="api_key_rotation",
        resource=result["key_id"],
        action="rotate",
        outcome="success",
        actor_fingerprint=principal.get("key_fingerprint"),
        actor_role=principal.get("role"),
        details={"role": request.role, "grace_seconds": request.grace_seconds},
    )
    return result


@app.post("/auth/keys/{key_id}/revoke")
def auth_key_revoke(key_id: str, http_request: Request) -> dict:
    """Revoke a database-managed API Key without exposing its secret hash."""
    if not DEFAULT_KEY_REGISTRY:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    principal = getattr(http_request.state, "auth_principal", {})
    try:
        revoked = DEFAULT_KEY_REGISTRY.revoke(
            key_id, actor=principal.get("key_fingerprint", "unknown")
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_audit(
        event_type="api_key_revocation",
        resource=key_id,
        action="revoke",
        outcome="success",
        actor_fingerprint=principal.get("key_fingerprint"),
        actor_role=principal.get("role"),
        details={"role": revoked.role},
    )
    return revoked.to_public_dict()


@app.get("/audit/events")
def audit_events(limit: int = 100, since: float | None = None) -> dict:
    """Return bounded redacted audit events for administrators."""
    if not DEFAULT_AUDIT_REPOSITORY:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    return {"events": DEFAULT_AUDIT_REPOSITORY.list(limit=limit, since=since)}


@app.get("/maintenance/retention/policy")
def retention_policy() -> dict:
    """Return effective retention periods and their environment controls."""
    if not DEFAULT_RETENTION_SERVICE:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    return {"policies": [item.to_dict() for item in DEFAULT_RETENTION_SERVICE.policies()]}


@app.post("/maintenance/retention/run")
def retention_run(request: RetentionRunRequest, http_request: Request) -> dict:
    """Dry-run or execute bounded trace/control-plane retention."""
    if not DEFAULT_RETENTION_SERVICE:
        raise HTTPException(status_code=503, detail="Shared database is not configured.")
    result = DEFAULT_RETENTION_SERVICE.run(
        dry_run=request.dry_run, batch_limit=request.batch_limit
    )
    principal = getattr(http_request.state, "auth_principal", {})
    _record_audit(
        event_type="retention",
        resource="control-plane",
        action="dry-run" if request.dry_run else "prune",
        outcome="success",
        actor_fingerprint=principal.get("key_fingerprint"),
        actor_role=principal.get("role"),
        details={"total_affected": result["total_affected"]},
    )
    return result


@app.get("/storage/status")
def control_plane_storage_status() -> dict:
    """Return redacted control-plane database health and backend type."""
    return storage_status(DEFAULT_CONTROL_PLANE_STORE)


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    """Expose bounded Prometheus metrics without user-query labels."""
    body = DEFAULT_METRICS.render(storage=storage_status(DEFAULT_CONTROL_PLANE_STORE))
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")


@app.post("/agent/query", response_model=AgentQueryResponse)
def agent_query(request: AgentQueryRequest) -> dict:
    """Run the Agent with deterministic planning."""
    return run_agent(
        request.query,
        persist_trajectory=request.persist_trajectory,
        session_id=request.session_id,
    )


@app.post("/agent/query-with-plan", response_model=AgentQueryResponse)
def agent_query_with_plan(request: AgentQueryWithPlanRequest) -> dict:
    """Run the Agent with an externally supplied LLM-style plan."""
    return run_agent(
        request.query,
        persist_trajectory=request.persist_trajectory,
        llm_plan_output=json.dumps(request.llm_plan, ensure_ascii=False),
        session_id=request.session_id,
    )


@app.post("/agent/query-provider")
def agent_query_provider(request: AgentProviderQueryRequest) -> dict:
    """Run optional online planning with validated deterministic fallback."""
    result = run_agent_with_provider(
        request.query,
        provider=request.provider,
        allow_fallback=request.allow_fallback,
        persist_trajectory=request.persist_trajectory,
        session_id=request.session_id,
    )
    if not result.get("provider", {}).get("execution_allowed", True):
        raise HTTPException(status_code=503, detail=result)
    AgentQueryResponse(**result)
    return result


@app.get("/providers/status")
def provider_status() -> dict:
    """Return provider availability without exposing credentials."""
    return DEFAULT_PLANNER_GATEWAY.status()


@app.get("/sessions/{session_id}")
def session_get(session_id: str) -> dict:
    """Return task-only context for one session."""
    context = DEFAULT_SESSION_REPOSITORY.get(session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found.")
    return context.to_dict()


@app.delete("/sessions/{session_id}")
def session_clear(session_id: str) -> dict:
    """Clear one session and its inherited task entities."""
    return {
        "session_id": session_id,
        "cleared": DEFAULT_SESSION_REPOSITORY.clear(session_id),
    }


@app.get("/traces/{trace_id}")
def trace_get(trace_id: str) -> dict:
    """Return an enhanced privacy-bounded Trace."""
    trace = DEFAULT_TRACE_REPOSITORY.get(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


@app.get("/traces/{trace_id}/replay-input")
def trace_replay_input(trace_id: str) -> dict:
    """Reconstruct the exact deterministic input for a Trace."""
    request = ReplayReader(DEFAULT_TRACE_REPOSITORY).reconstruct(trace_id)
    if not request:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return request


@app.post("/traces/{trace_id}/replay")
def trace_replay(trace_id: str) -> dict:
    """Replay a Trace with its resolved input in an isolated new session."""
    result = replay_trace(trace_id)
    if not result:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return result


@app.post("/feedback")
def feedback_submit(request: FeedbackSubmitRequest) -> dict:
    """Attach user feedback to an existing enhanced Trace."""
    try:
        return DEFAULT_FEEDBACK_LOOP.submit_feedback(
            trace_id=request.trace_id,
            rating=request.rating,
            expected_tool=request.expected_tool,
            issue_type=request.issue_type,
            comment=request.comment,
        ).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/feedback")
def feedback_list() -> dict:
    """List bounded in-memory Feedback records."""
    return {"feedback": DEFAULT_FEEDBACK_LOOP.list_feedback()}


@app.post("/candidates/propose")
def candidate_propose(request: CandidateProposeRequest) -> dict:
    """Generate a configuration-only candidate after the minimum feedback threshold."""
    try:
        return DEFAULT_FEEDBACK_LOOP.propose_candidate(request.fingerprint).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/candidates")
def candidate_list() -> dict:
    """List controlled policy candidates."""
    return {"candidates": DEFAULT_FEEDBACK_LOOP.list_candidates()}


@app.get("/candidates/{candidate_id}")
def candidate_get(candidate_id: str) -> dict:
    """Return one policy candidate and its gate report."""
    try:
        return DEFAULT_FEEDBACK_LOOP.get_candidate(candidate_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/candidates/{candidate_id}/evaluate")
def candidate_evaluate(candidate_id: str) -> dict:
    """Run linked replay and the frozen 193-case regression suite."""
    try:
        return DEFAULT_FEEDBACK_LOOP.evaluate_candidate(candidate_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/candidates/{candidate_id}/review")
def candidate_review(candidate_id: str, request: CandidateReviewRequest) -> dict:
    """Record a human approval/rejection without activating the candidate."""
    try:
        return DEFAULT_FEEDBACK_LOOP.review_candidate(
            candidate_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
        ).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/candidates/{candidate_id}/activate")
def candidate_activate(candidate_id: str) -> dict:
    """Explicitly block activation until Step 23 policy versioning exists."""
    try:
        DEFAULT_FEEDBACK_LOOP.activate_candidate(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"candidate_id": candidate_id, "active": False}


@app.post("/evolution/scan")
def evolution_scan() -> dict:
    """Mine offline failures, cluster causes, and generate safe draft candidates."""
    return DEFAULT_EVOLUTION_SERVICE.scan()


@app.get("/evolution/state")
def evolution_state() -> dict:
    """Return the current in-memory offline evolution cycle."""
    return DEFAULT_EVOLUTION_SERVICE.state()


@app.post("/evolution/candidates/{candidate_id}/shadow-evaluate")
def evolution_shadow_evaluate(candidate_id: str) -> dict:
    """Run linked cases and frozen regression cases without changing runtime policy."""
    try:
        return DEFAULT_EVOLUTION_SERVICE.evaluate_candidate(candidate_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/evolution/candidates/{candidate_id}/review")
def evolution_review(candidate_id: str, request: EvolutionReviewRequest) -> dict:
    """Record a human decision; approval still does not activate the candidate."""
    try:
        return DEFAULT_EVOLUTION_SERVICE.review_candidate(
            candidate_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
        ).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/evolution/candidates/{candidate_id}/activate")
def evolution_activate(candidate_id: str) -> dict:
    """Reject self-activation; reviewed release remains a separate human action."""
    try:
        DEFAULT_EVOLUTION_SERVICE.activate_candidate(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"candidate_id": candidate_id, "active": False}


@app.get("/policies")
def policy_list() -> dict:
    """List versioned policies and rollout state."""
    return DEFAULT_POLICY_RELEASE_SERVICE.state()


@app.get("/policies/assignment/{session_id}")
def policy_assignment(session_id: str) -> dict:
    """Return the deterministic policy assignment for a session."""
    return DEFAULT_POLICY_RELEASE_SERVICE.assignment(session_id)


@app.post("/policies/from-candidate/{candidate_id}")
def policy_from_candidate(candidate_id: str, request: PolicyReleaseRequest) -> dict:
    """Create a policy version and begin controlled rollout from an approved candidate."""
    try:
        return DEFAULT_POLICY_RELEASE_SERVICE.release_candidate(
            candidate_id,
            rollout_percentage=request.rollout_percentage,
            released_by=request.released_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/policies/{policy_id}/rollout")
def policy_rollout(policy_id: str, request: PolicyRolloutRequest) -> dict:
    """Change the rollout percentage without modifying source code."""
    try:
        return DEFAULT_POLICY_RELEASE_SERVICE.set_rollout(
            policy_id, request.rollout_percentage
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/policies/{policy_id}/promote")
def policy_promote(policy_id: str) -> dict:
    """Promote the current rollout policy to stable."""
    try:
        return DEFAULT_POLICY_RELEASE_SERVICE.promote(policy_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/policies/{policy_id}/rollback")
def policy_rollback(policy_id: str, request: PolicyRollbackRequest) -> dict:
    """Rollback by switching policy repository state, not source files."""
    try:
        return DEFAULT_POLICY_RELEASE_SERVICE.rollback(policy_id, reason=request.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/policies/{policy_id}/deprecate")
def policy_deprecate(policy_id: str) -> dict:
    """Deprecate an inactive policy version."""
    try:
        return DEFAULT_POLICY_RELEASE_SERVICE.deprecate(policy_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/policies/{policy_id}/monitor")
def policy_monitor(policy_id: str, request: PolicyMonitorSampleRequest) -> dict:
    """Record a rollout/control health sample and run rollback checks."""
    try:
        if not DEFAULT_POLICY_RELEASE_SERVICE.repository.get(policy_id):
            raise KeyError(f"Policy not found: {policy_id}")
        return DEFAULT_POLICY_RELEASE_SERVICE.record_monitor_sample(
            policy_id,
            success=request.success,
            latency_ms=request.latency_ms,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/evaluation/run", response_model=EvaluationResponse)
def evaluation_run() -> dict:
    """Run the benchmark and return metrics."""
    return run_evaluation()


@app.get("/evaluation/summary")
def evaluation_summary() -> dict:
    """Run all evaluation suites and return a compact summary."""
    return run_evaluation_summary()


@app.get("/evaluation/bad-cases")
def evaluation_bad_cases() -> dict:
    """Run the challenge suite and return bad-case optimization analysis."""
    return run_bad_case_analysis()


@app.get("/evaluation/robustness")
def evaluation_robustness() -> dict:
    """Run the ambiguous-query robustness suite."""
    return run_robustness_evaluation()


@app.get("/evaluation/experiment")
def evaluation_experiment() -> dict:
    """Run benchmark baseline and optimization experiment."""
    return run_benchmark_experiment()


@app.get("/evaluation/evidence")
def evaluation_evidence() -> dict:
    """Run Evidence normalization and Citation coverage evaluation."""
    return run_evidence_evaluation()


@app.get("/evaluation/verifier")
def evaluation_verifier() -> dict:
    """Run injected-error and partial-success Verifier evaluation."""
    return run_verifier_evaluation()


@app.get("/evaluation/rag")
def evaluation_rag() -> dict:
    """Compare legacy, BM25, and Hybrid document retrieval."""
    return run_rag_evaluation()


@app.get("/evaluation/context")
def evaluation_context() -> dict:
    """Run multi-turn Context, session isolation, and Trace replay evaluation."""
    return run_context_evaluation()


@app.get("/evaluation/feedback")
def evaluation_feedback() -> dict:
    """Run the controlled Feedback and candidate replay experiment."""
    return run_feedback_loop_evaluation()


@app.get("/evaluation/policy")
def evaluation_policy() -> dict:
    """Run policy rollout assignment and automatic rollback evaluation."""
    return run_policy_evaluation()


@app.get("/evaluation/provider")
def evaluation_provider() -> dict:
    """Run optional LLM provider parity and fallback evaluation."""
    return run_provider_evaluation()


@app.get("/evaluation/evolution")
def evaluation_evolution() -> dict:
    """Run offline failure mining, clustering, and shadow evaluation."""
    return run_evolution_evaluation()


@app.get("/evaluation/control-plane")
def evaluation_control_plane() -> dict:
    """Run persistence, authorization, and multi-worker consistency gates."""
    return run_control_plane_evaluation()


@app.get("/tools", response_model=ToolListResponse)
def tools() -> dict:
    """Return tool schemas."""
    return {
        "tools": export_tool_schemas()
    }


@app.get("/function-specs")
def function_specs() -> dict:
    """Return function-calling friendly tool specs."""
    return {
        "functions": build_function_specs()
    }
