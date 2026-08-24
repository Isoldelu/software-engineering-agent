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
