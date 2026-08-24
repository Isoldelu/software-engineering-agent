"""Orchestrate offline mining, safe candidate generation, shadow eval, and review."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.evolution.candidate import EvolutionCandidateFactory, ShadowEvaluator
from app.evolution.miner import OfflineFailureMiner
from app.evolution.models import EvolutionCandidate
from app.evolution.repository import DEFAULT_EVOLUTION_REPOSITORY, EvolutionRepository


class OfflineEvolutionService:
    def __init__(
        self,
        *,
        repository: EvolutionRepository | None = None,
        miner: OfflineFailureMiner | None = None,
    ) -> None:
        self.repository = repository or EvolutionRepository()
        self.miner = miner or OfflineFailureMiner()
        self.factory = EvolutionCandidateFactory()
        self.evaluator = ShadowEvaluator()

    def scan(self) -> dict[str, Any]:
        with self.repository.cycle_lease():
            self.repository.clear()
            failures, clusters = self.miner.mine()
            for failure in failures:
                self.repository.save_failure(failure)
            for cluster in clusters:
                self.repository.save_cluster(cluster)
                self.repository.save_candidate(self.factory.build(cluster, created_at=_now()))
            return self.state()

    def evaluate_candidate(self, candidate_id: str) -> EvolutionCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.status not in {"draft", "rejected"}:
            raise ValueError(f"Candidate cannot be shadow-evaluated from {candidate.status}.")
        candidate.status = "shadow_evaluating"
        self.repository.save_candidate(candidate)
        candidate.shadow_evaluation = self.evaluator.evaluate(
            candidate,
            self.repository.failures(),
        )
        candidate.status = candidate.shadow_evaluation["next_status"]
        return self.repository.save_candidate(candidate)

    def evaluate_all(self) -> list[EvolutionCandidate]:
        return [
            self.evaluate_candidate(candidate.candidate_id)
            for candidate in self.repository.candidates()
            if candidate.status in {"draft", "rejected"}
        ]

    def review_candidate(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewer: str,
        note: str = "",
    ) -> EvolutionCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.status != "pending_review":
            raise ValueError("Only pending_review candidates can be reviewed.")
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        if not reviewer.strip():
            raise ValueError("reviewer is required")
        candidate.status = "approved" if decision == "approve" else "rejected"
        candidate.review = {
            "decision": decision,
            "reviewer": reviewer,
            "note": note,
            "reviewed_at": _now(),
            "activation_status": "not_activated_manual_release_required",
        }
        candidate.active = False
        return self.repository.save_candidate(candidate)

    def activate_candidate(self, candidate_id: str) -> None:
        self._candidate(candidate_id)
        raise PermissionError(
            "Offline evolution candidates cannot self-activate; use a reviewed release path."
        )

    def state(self) -> dict[str, Any]:
        failures = self.repository.failures()
        clusters = self.repository.clusters()
        candidates = self.repository.candidates()
        return {
            "mode": "offline_controlled",
            "failure_count": len(failures),
            "cluster_count": len(clusters),
            "candidate_count": len(candidates),
            "failures": [item.to_dict() for item in failures],
            "clusters": [item.to_dict() for item in clusters],
            "candidates": [item.to_dict() for item in candidates],
            "automatic_source_changes": False,
            "automatic_activation": False,
            "human_review_required": True,
        }

    def get_candidate(self, candidate_id: str) -> EvolutionCandidate:
        return self._candidate(candidate_id)

    def _candidate(self, candidate_id: str) -> EvolutionCandidate:
        candidate = self.repository.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"Evolution candidate not found: {candidate_id}")
        return candidate


def _now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_EVOLUTION_SERVICE = OfflineEvolutionService(repository=DEFAULT_EVOLUTION_REPOSITORY)
