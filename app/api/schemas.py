"""API request and response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    query: str = Field(..., description="Natural-language software engineering query.")
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier used for task-entity inheritance.",
    )
    persist_trajectory: bool = Field(
        default=False,
        description="Whether to append the Agent trajectory to data/trajectories.jsonl."
    )


class AgentQueryWithPlanRequest(AgentQueryRequest):
    llm_plan: dict[str, Any] = Field(
        ...,
        description="LLM-style JSON tool plan to validate and execute."
    )


class AgentProviderQueryRequest(AgentQueryRequest):
    provider: Literal["auto", "offline", "openai"] = "auto"
    allow_fallback: bool = True


class AgentQueryResponse(BaseModel):
    query: str
    intent: str
    selected_tool: str
    answer: str
    used_tools: list[str]
    tool_call_count: int
    evidence: list[str]
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_count: int = 0
    execution_status: str = "success"
    verification: dict[str, Any] = Field(default_factory=dict)
    confidence: str
    success: bool
    plan: list[dict[str, Any]]
    trajectory: list[dict[str, Any]]
    session_id: str | None = None
    trace_id: str | None = None
    parent_trace_id: str | None = None
    resolved_query: str | None = None
    inherited_context: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    trace_schema_version: str | None = None
    policy_version: str | None = None
    policy_assignment: dict[str, Any] = Field(default_factory=dict)
    policy_monitor_event: dict[str, Any] | None = None
    provider: dict[str, Any] = Field(default_factory=dict)
    replayable: bool = False


class HealthResponse(BaseModel):
    status: str
    service: str


class ToolListResponse(BaseModel):
    tools: list[dict[str, Any]]


class FeedbackSubmitRequest(BaseModel):
    trace_id: str
    rating: Literal[-1, 1]
    expected_tool: str | None = None
    issue_type: str | None = None
    comment: str = ""


class CandidateProposeRequest(BaseModel):
    fingerprint: str | None = None


class CandidateReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    note: str = ""


class EvolutionReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str
    note: str = ""


class EvolutionPolicyReleaseRequest(BaseModel):
    rollout_percentage: float = Field(default=20.0, gt=0, le=100)
    released_by: str = Field(..., min_length=1)


class PolicyReleaseRequest(BaseModel):
    rollout_percentage: float = Field(default=20.0, gt=0, le=100)
    released_by: str


class PolicyRolloutRequest(BaseModel):
    rollout_percentage: float = Field(..., gt=0, le=100)


class PolicyRollbackRequest(BaseModel):
    reason: str


class PolicyMonitorSampleRequest(BaseModel):
    success: bool
    latency_ms: float = Field(default=0.0, ge=0)


class ApiKeyRotateRequest(BaseModel):
    role: Literal["reader", "operator", "admin"]
    grace_seconds: float = Field(default=300.0, ge=0, le=86_400)
    ttl_seconds: float | None = Field(default=None, gt=0)


class RetentionRunRequest(BaseModel):
    dry_run: bool = True
    batch_limit: int = Field(default=1000, ge=1, le=10_000)


class EvaluationResponse(BaseModel):
    benchmark: str
    total: int
    tool_routing_accuracy: float
    task_success_rate: float
    answer_grounding_accuracy: float
    answer_accuracy: float
    average_tool_calls: float
    bad_cases: list[dict[str, Any]]
    results: list[dict[str, Any]]
