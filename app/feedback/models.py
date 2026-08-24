"""Stable models for Feedback records and configuration-only candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_ISSUE_TYPES = {
    "wrong_tool",
    "tool_execution_failed",
    "answer_not_grounded",
    "answer_incomplete",
    "verification_failed",
}
VALID_CANDIDATE_STATUSES = {
    "draft",
    "replaying",
    "pending_review",
    "approved",
    "rejected",
}
ALLOWED_ASSET_TYPES = {
    "router_hook",
    "planner_skill",
    "argument_rule",
    "reranker_weights",
    "answer_rule",
    "verifier_rule",
}


@dataclass
class FeedbackRecord:
    feedback_id: str
    trace_id: str
    rating: int
    issue_type: str
    expected_tool: str | None
    comment: str
    status: str
    fingerprint: str
    observed: dict[str, Any]
    created_at: str
    candidate_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyCandidate:
    candidate_id: str
    schema_version: str
    asset_type: str
    status: str
    source_feedback_ids: list[str]
    fingerprint: str
    config: dict[str, Any]
    safety_scope: dict[str, Any]
    created_at: str
    evaluation: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
