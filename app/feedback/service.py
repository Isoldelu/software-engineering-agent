"""Orchestration service for controlled Feedback, candidate replay, and review."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.agent.llm_router import VALID_TOOLS
from app.agent.trace import DEFAULT_TRACE_REPOSITORY, TraceRepository
from app.feedback.classifier import BadCaseClassifier, FeedbackObserver
from app.feedback.models import FeedbackRecord, PolicyCandidate
from app.feedback.policy import CandidateEvaluator
from app.feedback.repository import (
    DEFAULT_CANDIDATE_REPOSITORY,
    DEFAULT_FEEDBACK_REPOSITORY,
    CandidateRepository,
    FeedbackRepository,
)


class ControlledFeedbackLoop:
    def __init__(
        self,
        *,
        traces: TraceRepository,
        feedback: FeedbackRepository,
        candidates: CandidateRepository,
        minimum_feedback: int = 3,
    ) -> None:
        self.traces = traces
        self.feedback = feedback
        self.candidates = candidates
        self.minimum_feedback = minimum_feedback
        self.observer = FeedbackObserver(traces)
        self.classifier = BadCaseClassifier()

    def submit_feedback(
        self,
        *,
        trace_id: str,
        rating: int,
        expected_tool: str | None = None,
        issue_type: str | None = None,
        comment: str = "",
    ) -> FeedbackRecord:
        if rating not in {-1, 1}:
            raise ValueError("rating must be -1 or 1")
        if expected_tool and expected_tool not in VALID_TOOLS:
            raise ValueError(f"Unknown expected tool: {expected_tool}")
        observed = self.observer.observe(trace_id)
        classification = self.classifier.classify(
            observed,
            expected_tool=expected_tool,
            issue_type=issue_type,
        )
        observed["classification"] = classification
        record = FeedbackRecord(
            feedback_id=f"fb_{uuid.uuid4().hex[:18]}",
            trace_id=trace_id,
            rating=rating,
            issue_type=classification["issue_type"],
            expected_tool=expected_tool,
            comment=comment,
            status="open",
            fingerprint=classification["fingerprint"],
            observed=observed,
            created_at=_now(),
        )
        return self.feedback.save(record)

    def propose_candidate(self, fingerprint: str | None = None) -> PolicyCandidate:
        records = [item for item in self.feedback.list() if item.rating == -1 and item.status == "open"]
        if fingerprint:
            records = [item for item in records if item.fingerprint == fingerprint]
        elif records:
            counts = Counter(item.fingerprint for item in records)
            fingerprint = counts.most_common(1)[0][0]
            records = [item for item in records if item.fingerprint == fingerprint]
        if len(records) < self.minimum_feedback:
            raise ValueError(
                f"At least {self.minimum_feedback} matching negative feedback records are required."
            )
        if any(item.issue_type != "wrong_tool" for item in records):
            raise ValueError("The current proposer supports wrong_tool router hooks only.")
        expected_tools = {item.expected_tool for item in records}
        triggers = {item.observed["classification"]["trigger"] for item in records}
        if len(expected_tools) != 1 or None in expected_tools or len(triggers) != 1 or None in triggers:
            raise ValueError("Feedback group does not have one deterministic tool/trigger pair.")
        expected_tool = expected_tools.pop()
        trigger = triggers.pop()
        candidate = PolicyCandidate(
            candidate_id=f"cand_{uuid.uuid4().hex[:18]}",
            schema_version="policy-candidate-v1",
            asset_type="router_hook",
            status="draft",
            source_feedback_ids=[item.feedback_id for item in records],
            fingerprint=fingerprint or records[0].fingerprint,
            config={
                "rules": [{
                    "hook_id": f"hook_{trigger}_{expected_tool}",
                    "match": {"terms": [trigger], "mode": "any"},
                    "action": {"intent": expected_tool, "tool": expected_tool},
                    "priority": 100,
                }],
            },
            safety_scope={
                "allowed_changes": ["router_hook_config"],
                "forbidden_changes": [
                    "python_source", "datasets", "test_assertions", "permissions", "release_gates"
                ],
                "automatic_activation": False,
            },
            created_at=_now(),
        )
        candidate = self.candidates.save(candidate)
        for record in records:
            record.status = "candidate_created"
            record.candidate_id = candidate.candidate_id
            self.feedback.save(record)
        return candidate

    def evaluate_candidate(self, candidate_id: str) -> PolicyCandidate:
        candidate = self._candidate(candidate_id)
        if candidate.status not in {"draft", "rejected"}:
            raise ValueError(f"Candidate cannot be evaluated from status {candidate.status}.")
        candidate.status = "replaying"
        self.candidates.save(candidate)
        linked = [
            record for record in self.feedback.list()
            if record.feedback_id in candidate.source_feedback_ids
        ]
        candidate.evaluation = CandidateEvaluator().evaluate(candidate, linked)
        candidate.status = candidate.evaluation["next_status"]
        return self.candidates.save(candidate)

    def review_candidate(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewer: str,
        note: str = "",
    ) -> PolicyCandidate:
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
            "activation_status": "not_activated_step23_required",
        }
        candidate.active = False
        return self.candidates.save(candidate)

    def activate_candidate(self, candidate_id: str) -> None:
        self._candidate(candidate_id)
        raise PermissionError(
            "Step 22 candidates cannot be activated. Step 23 policy versioning and rollout are required."
        )

    def list_feedback(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.feedback.list()]

    def list_candidates(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.candidates.list()]

    def get_candidate(self, candidate_id: str) -> PolicyCandidate:
        return self._candidate(candidate_id)

    def _candidate(self, candidate_id: str) -> PolicyCandidate:
        candidate = self.candidates.get(candidate_id)
        if not candidate:
            raise KeyError(f"Candidate not found: {candidate_id}")
        return candidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_FEEDBACK_LOOP = ControlledFeedbackLoop(
    traces=DEFAULT_TRACE_REPOSITORY,
    feedback=DEFAULT_FEEDBACK_REPOSITORY,
    candidates=DEFAULT_CANDIDATE_REPOSITORY,
)
