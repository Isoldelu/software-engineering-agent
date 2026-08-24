"""Models for versioned Agent policy rollout."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_POLICY_STATUSES = {"draft", "rollout", "active", "deprecated", "rolled_back"}


@dataclass
class PolicyVersion:
    policy_id: str
    version: int
    status: str
    config: dict[str, Any]
    rollout_percentage: float
    parent_policy_id: str | None
    source_candidate_id: str | None
    created_at: str
    activated_at: str | None = None
    deprecated_at: str | None = None
    rolled_back_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyAssignment:
    policy_id: str
    version: int
    cohort: str
    bucket: float
    rollout_percentage: float
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
