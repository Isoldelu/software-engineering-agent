"""Provider-aware entry point that preserves the existing Agent workflow."""

from __future__ import annotations

from app.agent.workflow import run_agent
from app.providers.gateway import DEFAULT_PLANNER_GATEWAY, PlannerGateway


def run_agent_with_provider(
    query: str,
    *,
    provider: str = "auto",
    allow_fallback: bool = True,
    persist_trajectory: bool = False,
    session_id: str | None = None,
    gateway: PlannerGateway | None = None,
) -> dict:
    planner_gateway = gateway or DEFAULT_PLANNER_GATEWAY
    decision = planner_gateway.plan(
        query,
        provider=provider,
        allow_fallback=allow_fallback,
    )
    if not decision.metadata.get("execution_allowed", True):
        return {
            "query": query,
            "execution_status": "failed",
            "success": False,
            "answer": "The requested planning provider failed and fallback is disabled.",
            "provider": decision.metadata,
        }
    return run_agent(
        query,
        persist_trajectory=persist_trajectory,
        llm_plan_output=decision.plan_output,
        session_id=session_id,
        planner_metadata=decision.metadata,
    )
