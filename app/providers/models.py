"""Provider request, result, and planner decision models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderRequest:
    query: str
    prompt: str
    timeout_seconds: float
    max_output_tokens: int


@dataclass
class ProviderResult:
    provider: str
    status: str
    plan_output: str | None
    model: str | None = None
    latency_ms: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("plan_output", None)
        return payload


@dataclass(frozen=True)
class PlannerDecision:
    plan_output: str | None
    metadata: dict[str, Any]
