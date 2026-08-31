"""Policy release lifecycle from approved candidate to rollout and rollback."""

from __future__ import annotations

from typing import Any

from app.evolution.repository import (
    DEFAULT_EVOLUTION_REPOSITORY,
    EvolutionRepository,
)
from app.feedback.policy import CandidateConfigValidator
from app.feedback.repository import DEFAULT_CANDIDATE_REPOSITORY, CandidateRepository
from app.policy.engine import (
    DEFAULT_POLICY_ENGINE,
    DEFAULT_POLICY_REPOSITORY,
    PolicyConfigValidator,
    PolicyEngine,
)
from app.policy.repository import PolicyRepository


class PolicyReleaseService:
    def __init__(
        self,
        *,
        repository: PolicyRepository,
        engine: PolicyEngine,
        candidates: CandidateRepository,
        evolution_candidates: EvolutionRepository | None = None,
    ) -> None:
        self.repository = repository
        self.engine = engine
        self.candidates = candidates
        self.evolution_candidates = evolution_candidates

    def release_candidate(
        self,
        candidate_id: str,
        *,
        rollout_percentage: float,
        released_by: str,
    ) -> dict[str, Any]:
        candidate = self.candidates.get(candidate_id)
        if not candidate:
            raise KeyError(f"Candidate not found: {candidate_id}")
        if candidate.status != "approved":
            raise ValueError("Only an approved candidate can create a policy version.")
        if candidate.active:
            raise ValueError("Candidate already has an active or rollout policy.")
        candidate_issues = CandidateConfigValidator().validate(candidate)
        policy_issues = PolicyConfigValidator().validate(candidate.config)
        if candidate_issues or policy_issues:
            raise ValueError(f"Invalid candidate config: {candidate_issues + policy_issues}")
        policy = self.repository.create(
            config=candidate.config,
            source_candidate_id=candidate_id,
            metadata={
                "released_by": released_by,
                "candidate_evaluation": candidate.evaluation,
            },
        )
        policy = self.repository.start_rollout(policy.policy_id, rollout_percentage)
        candidate.active = True
        candidate.review["activation_status"] = "rollout"
        candidate.review["policy_id"] = policy.policy_id
        self.candidates.save(candidate)
        return {
            "policy": policy.to_dict(),
            "assignment_state": self.repository.state(),
        }

    def set_rollout(self, policy_id: str, percentage: float) -> dict[str, Any]:
        return self.repository.set_rollout_percentage(policy_id, percentage).to_dict()

    def promote(self, policy_id: str) -> dict[str, Any]:
        policy = self.repository.promote(policy_id)
        self._set_candidate_status(policy.source_candidate_id, "active", active=True)
        return policy.to_dict()

    def rollback(self, policy_id: str, *, reason: str) -> dict[str, Any]:
        policy = self.repository.rollback(policy_id, reason=reason)
        self._deactivate_candidate(policy.source_candidate_id, "rolled_back")
        return {
            "policy": policy.to_dict(),
            "state": self.repository.state(),
        }

    def deprecate(self, policy_id: str) -> dict[str, Any]:
        return self.repository.deprecate(policy_id).to_dict()

    def assignment(self, session_id: str) -> dict[str, Any]:
        return self.engine.assign(session_id).to_dict()

    def record_monitor_sample(
        self,
        policy_id: str,
        *,
        success: bool,
        latency_ms: float,
    ) -> dict[str, Any]:
        self.engine.monitor.record(policy_id, success=success, latency_ms=latency_ms)
        event = self.engine.monitor.evaluate(self.repository)
        if event and event["action"] == "rollback":
            policy = self.repository.get(policy_id)
            if policy:
                self._deactivate_candidate(policy.source_candidate_id, "automatic_rollback")
        return {
            "metrics": self.engine.monitor.metrics(policy_id),
            "event": event,
            "state": self.repository.state(),
        }

    def state(self) -> dict[str, Any]:
        state = self.repository.state()
        state["monitor_events"] = list(self.engine.monitor.events)
        state["policy_metrics"] = {
            item.policy_id: self.engine.monitor.metrics(item.policy_id)
            for item in self.repository.list()
        }
        return state

    def _deactivate_candidate(self, candidate_id: str | None, status: str) -> None:
        self._set_candidate_status(candidate_id, status, active=False)

    def _set_candidate_status(
        self,
        candidate_id: str | None,
        status: str,
        *,
        active: bool,
    ) -> None:
        if not candidate_id:
            return
        if candidate_id.startswith("evolution:") and self.evolution_candidates:
            parts = candidate_id.split(":", 2)
            if len(parts) < 2:
                return
            evolution_candidate = self.evolution_candidates.get_candidate(parts[1])
            if not evolution_candidate:
                return
            evolution_candidate.active = active
            evolution_candidate.review["activation_status"] = status
            self.evolution_candidates.save_candidate(evolution_candidate)
            return
        feedback_candidate = self.candidates.get(candidate_id)
        if not feedback_candidate:
            return
        feedback_candidate.active = active
        feedback_candidate.review["activation_status"] = status
        self.candidates.save(feedback_candidate)


DEFAULT_POLICY_RELEASE_SERVICE = PolicyReleaseService(
    repository=DEFAULT_POLICY_REPOSITORY,
    engine=DEFAULT_POLICY_ENGINE,
    candidates=DEFAULT_CANDIDATE_REPOSITORY,
    evolution_candidates=DEFAULT_EVOLUTION_REPOSITORY,
)
