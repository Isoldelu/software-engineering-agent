"""Models for mined failures, clusters, and configuration candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

VALID_EVOLUTION_ASSETS = {"router_rule", "query_alias", "retriever_weights"}
VALID_EVOLUTION_STATUSES = {
    "draft",
    "shadow_evaluating",
    "pending_review",
    "approved",
    "rejected",
}


@dataclass
class MinedFailure:
    failure_id: str
    source: str
    case_id: str
    query: str
    issue_type: str
    cluster_key: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    candidate_signal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureCluster:
    cluster_id: str
    issue_type: str
    cluster_key: str
    failure_ids: list[str]
    support: int
    candidate_asset_type: str
    signal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionCandidate:
    candidate_id: str
    schema_version: str
    asset_type: str
    status: str
    source_cluster_id: str
    source_failure_ids: list[str]
    config: dict[str, Any]
    safety_scope: dict[str, Any]
    created_at: str
    shadow_evaluation: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionPolicyBridge:
    bridge_id: str
    schema_version: str
    candidate_id: str
    candidate_digest: str
    policy_source_id: str
    policy_id: str
    policy_version: int
    rollout_percentage: float
    released_by: str
    reviewer: str
    config_digest: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceQualityAssessment:
    assessment_id: str
    schema_version: str
    batch_id: str
    trace_id: str
    quality_score: float
    low_quality: bool
    actionable: bool
    signals: list[str]
    feedback_ids: list[str]
    expected_tool: str | None
    fingerprint: str | None
    assessed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContinuousEvolutionCycle:
    cycle_id: str
    schema_version: str
    status: str
    started_at: str
    completed_at: str
    cursor_before: str | None
    cursor_after: str | None
    trace_count: int
    low_quality_count: int
    actionable_count: int
    profile: dict[str, Any]
    drift: dict[str, Any]
    candidate_ids: list[str]
    gates: dict[str, bool]
    automatic_activation: bool = False
    human_review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
