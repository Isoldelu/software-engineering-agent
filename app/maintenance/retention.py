"""Bounded retention policies for traces and control-plane records."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from app.observability.metrics import DEFAULT_METRICS
from app.security.audit import AuditRepository
from app.storage.database import ControlPlaneStore

DAY_SECONDS = 86_400
DEFAULT_RETENTION_DAYS = {
    "session": 7,
    "trace": 30,
    "feedback": 90,
    "policy_candidate": 90,
    "evolution_failure": 30,
    "evolution_cluster": 30,
    "evolution_candidate": 90,
    "audit": 180,
}


@dataclass(frozen=True)
class RetentionPolicy:
    namespace: str
    days: int

    @property
    def environment(self) -> str:
        name = self.namespace.upper().replace("-", "_")
        return f"SOFTWARE_AGENT_RETENTION_{name}_DAYS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "days": self.days,
            "environment": self.environment,
        }


class RetentionService:
    def __init__(self, store: ControlPlaneStore) -> None:
        self.store = store
        self.audit = AuditRepository(store)

    def policies(self) -> list[RetentionPolicy]:
        result = []
        for namespace, default_days in DEFAULT_RETENTION_DAYS.items():
            environment = f"SOFTWARE_AGENT_RETENTION_{namespace.upper()}_DAYS"
            value = os.getenv(environment, str(default_days))
            try:
                days = int(value)
            except ValueError as exc:
                raise ValueError(f"{environment} must be an integer.") from exc
            if days <= 0:
                raise ValueError(f"{environment} must be positive.")
            result.append(RetentionPolicy(namespace, days))
        return result

    def run(
        self,
        *,
        dry_run: bool = True,
        batch_limit: int = 1000,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = now if now is not None else time.time()
        bounded_limit = max(1, min(int(batch_limit), 10_000))
        results = []
        for policy in self.policies():
            cutoff = current - policy.days * DAY_SECONDS
            if policy.namespace == "audit":
                affected = self.audit.prune(
                    older_than=cutoff, limit=bounded_limit, dry_run=dry_run
                )
            else:
                affected = self.store.prune_older_than(
                    policy.namespace,
                    cutoff,
                    limit=bounded_limit,
                    dry_run=dry_run,
                )
            results.append(
                {
                    "namespace": policy.namespace,
                    "retention_days": policy.days,
                    "cutoff": cutoff,
                    "affected": affected,
                }
            )
            if not dry_run:
                DEFAULT_METRICS.observe_retention(policy.namespace, affected)
        return {
            "dry_run": dry_run,
            "batch_limit": bounded_limit,
            "total_affected": sum(item["affected"] for item in results),
            "results": results,
        }
