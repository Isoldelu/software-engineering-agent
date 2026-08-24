"""Rollout/control monitoring with deterministic automatic rollback."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from app.policy.repository import PolicyRepository


class PolicyMonitor:
    def __init__(
        self,
        *,
        min_samples: int = 5,
        max_samples: int = 100,
        max_success_rate_drop: float = 0.10,
        minimum_rollout_success_rate: float = 0.80,
    ) -> None:
        self.min_samples = min_samples
        self.max_success_rate_drop = max_success_rate_drop
        self.minimum_rollout_success_rate = minimum_rollout_success_rate
        self._records: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_samples)
        )
        self.events: list[dict[str, Any]] = []

    def record(self, policy_id: str, *, success: bool, latency_ms: float) -> None:
        self._records[policy_id].append({
            "success": bool(success),
            "latency_ms": max(0.0, float(latency_ms)),
        })

    def evaluate(self, repository: PolicyRepository) -> dict[str, Any] | None:
        rollout = repository.rollout()
        if not rollout:
            return None
        control_id = repository.stable_policy_id
        control = list(self._records[control_id])
        treatment = list(self._records[rollout.policy_id])
        if len(control) < self.min_samples or len(treatment) < self.min_samples:
            return None
        control_rate = _success_rate(control)
        rollout_rate = _success_rate(treatment)
        should_rollback = (
            rollout_rate < self.minimum_rollout_success_rate
            or control_rate - rollout_rate > self.max_success_rate_drop
        )
        event = {
            "event": "rollout_health_check",
            "policy_id": rollout.policy_id,
            "control_policy_id": control_id,
            "control_samples": len(control),
            "rollout_samples": len(treatment),
            "control_success_rate": control_rate,
            "rollout_success_rate": rollout_rate,
            "action": "rollback" if should_rollback else "continue",
        }
        if should_rollback:
            repository.rollback(
                rollout.policy_id,
                reason=(
                    f"automatic monitor rollback: rollout success {rollout_rate:.3f}, "
                    f"control success {control_rate:.3f}"
                ),
            )
        self.events.append(event)
        return event

    def metrics(self, policy_id: str) -> dict[str, Any]:
        records = list(self._records[policy_id])
        return {
            "policy_id": policy_id,
            "sample_count": len(records),
            "success_rate": _success_rate(records),
            "average_latency_ms": (
                sum(item["latency_ms"] for item in records) / len(records)
                if records else 0.0
            ),
        }


def _success_rate(records: list[dict[str, Any]]) -> float:
    return sum(item["success"] for item in records) / len(records) if records else 1.0
