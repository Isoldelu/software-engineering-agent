"""Trace-driven continuous shadow evolution with human-gated delivery."""

from __future__ import annotations

import hashlib
import math
import threading
import uuid
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.agent.trace import DEFAULT_TRACE_REPOSITORY, TraceRepository
from app.evolution.candidate import EvolutionCandidateFactory, ShadowEvaluator
from app.evolution.models import (
    ContinuousEvolutionCycle,
    FailureCluster,
    MinedFailure,
    TraceQualityAssessment,
)
from app.evolution.repository import DEFAULT_EVOLUTION_REPOSITORY, EvolutionRepository
from app.feedback.models import FeedbackRecord
from app.feedback.repository import DEFAULT_FEEDBACK_REPOSITORY, FeedbackRepository
from app.storage.database import DEFAULT_CONTROL_PLANE_STORE, ControlPlaneStore

CONTINUOUS_STATE_NAMESPACE = "continuous_evolution_state"
CONTINUOUS_CYCLE_NAMESPACE = "continuous_evolution_cycle"
CONTINUOUS_ASSESSMENT_NAMESPACE = "continuous_trace_assessment"
CONTINUOUS_STATE_ID = "default"


class TraceQualityScorer:
    """Score observable execution quality without model judgment or hidden thought."""

    def __init__(self, *, low_quality_threshold: float = 0.75) -> None:
        self.low_quality_threshold = low_quality_threshold

    def assess(
        self,
        trace: dict[str, Any],
        feedback: list[FeedbackRecord],
        *,
        batch_id: str,
        assessed_at: str,
    ) -> TraceQualityAssessment:
        score = 1.0
        signals: list[str] = []
        output = trace.get("output", {})
        status = output.get("execution_status")
        evidence_ids = output.get("evidence_ids", [])
        verification = output.get("verification", {})
        steps = trace.get("steps", [])

        if status == "failed":
            score -= 0.55
            signals.append("execution_failed")
        elif status == "partial_success":
            score -= 0.25
            signals.append("partial_success")
        if status == "success" and not evidence_ids:
            score -= 0.3
            signals.append("success_without_evidence")
        if verification and not verification.get("passed", True):
            score -= 0.4
            signals.append("verification_failed")
        step_keys = [(item.get("tool"), item.get("input")) for item in steps]
        if len(step_keys) != len(set(step_keys)):
            score -= 0.2
            signals.append("duplicate_tool_call")

        negative = [item for item in feedback if item.rating == -1]
        if negative:
            score -= 0.5
            signals.append("negative_feedback")
            signals.extend(f"feedback_{item.issue_type}" for item in negative)

        actionable_feedback = [
            item
            for item in negative
            if item.issue_type == "wrong_tool"
            and item.expected_tool
            and item.expected_tool != trace.get("plan", {}).get("tool")
            and item.observed.get("classification", {}).get("trigger")
        ]
        expected_tools = {item.expected_tool for item in actionable_feedback}
        fingerprints = {item.fingerprint for item in actionable_feedback}
        actionable = len(expected_tools) == 1 and len(fingerprints) == 1
        expected_tool = next(iter(expected_tools)) if actionable else None
        fingerprint = next(iter(fingerprints)) if actionable else None
        bounded_score = round(max(0.0, min(1.0, score)), 4)
        trace_id = str(trace["trace_id"])
        return TraceQualityAssessment(
            assessment_id=f"assessment_{_digest(f'{batch_id}:{trace_id}')}",
            schema_version="trace-quality-v1",
            batch_id=batch_id,
            trace_id=trace_id,
            quality_score=bounded_score,
            low_quality=bounded_score < self.low_quality_threshold,
            actionable=actionable,
            signals=sorted(set(signals)),
            feedback_ids=sorted(item.feedback_id for item in negative),
            expected_tool=expected_tool,
            fingerprint=fingerprint,
            assessed_at=assessed_at,
        )


class TraceDriftDetector:
    """Compare a bounded trace batch with the last healthy reference profile."""

    def __init__(
        self,
        *,
        quality_drop_threshold: float = 0.15,
        low_quality_rate_delta: float = 0.25,
        failure_rate_delta: float = 0.15,
        tool_distribution_delta: float = 0.4,
        latency_ratio_delta: float = 0.5,
        latency_noise_floor_ms: float = 10.0,
        minimum_reference_quality: float = 0.9,
        maximum_reference_low_quality_rate: float = 0.1,
        maximum_reference_failure_rate: float = 0.05,
    ) -> None:
        self.quality_drop_threshold = quality_drop_threshold
        self.low_quality_rate_delta = low_quality_rate_delta
        self.failure_rate_delta = failure_rate_delta
        self.tool_distribution_delta = tool_distribution_delta
        self.latency_ratio_delta = latency_ratio_delta
        self.latency_noise_floor_ms = latency_noise_floor_ms
        self.minimum_reference_quality = minimum_reference_quality
        self.maximum_reference_low_quality_rate = maximum_reference_low_quality_rate
        self.maximum_reference_failure_rate = maximum_reference_failure_rate

    def profile(
        self,
        traces: list[dict[str, Any]],
        assessments: list[TraceQualityAssessment],
    ) -> dict[str, Any]:
        count = len(traces)
        distribution = Counter(str(item.get("plan", {}).get("tool", "unknown")) for item in traces)
        latencies = [float(item.get("metrics", {}).get("total_latency_ms", 0.0)) for item in traces]
        failures = sum(
            item.get("output", {}).get("execution_status") == "failed" for item in traces
        )
        negatives = sum("negative_feedback" in item.signals for item in assessments)
        return {
            "trace_count": count,
            "mean_quality_score": round(
                sum(item.quality_score for item in assessments) / count if count else 0.0,
                4,
            ),
            "low_quality_rate": round(
                sum(item.low_quality for item in assessments) / count if count else 0.0,
                4,
            ),
            "failure_rate": round(failures / count if count else 0.0, 4),
            "negative_feedback_rate": round(negatives / count if count else 0.0, 4),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
            "tool_distribution": {
                key: round(value / count, 4)
                for key, value in sorted(distribution.items())
            } if count else {},
        }

    def detect(
        self,
        profile: dict[str, Any],
        reference: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if reference is None:
            reference_healthy = (
                profile["mean_quality_score"] >= self.minimum_reference_quality
                and profile["low_quality_rate"] <= self.maximum_reference_low_quality_rate
                and profile["failure_rate"] <= self.maximum_reference_failure_rate
            )
            return {
                "reference_available": False,
                "detected": not reference_healthy,
                "signals": [
                    "reference_initialized"
                    if reference_healthy else "absolute_quality_threshold_breached"
                ],
                "deltas": {},
            }
        quality_drop = reference["mean_quality_score"] - profile["mean_quality_score"]
        low_quality_delta = profile["low_quality_rate"] - reference["low_quality_rate"]
        failure_delta = profile["failure_rate"] - reference["failure_rate"]
        tool_delta = _distribution_distance(
            reference["tool_distribution"], profile["tool_distribution"]
        )
        latency_delta = profile["p95_latency_ms"] - reference["p95_latency_ms"]
        latency_ratio = latency_delta / max(reference["p95_latency_ms"], 1.0)
        signals = []
        if quality_drop >= self.quality_drop_threshold:
            signals.append("quality_score_drop")
        if low_quality_delta >= self.low_quality_rate_delta:
            signals.append("low_quality_rate_increase")
        if failure_delta >= self.failure_rate_delta:
            signals.append("failure_rate_increase")
        if tool_delta >= self.tool_distribution_delta:
            signals.append("tool_distribution_shift")
        if (
            latency_delta >= self.latency_noise_floor_ms
            and latency_ratio >= self.latency_ratio_delta
        ):
            signals.append("p95_latency_increase")
        return {
            "reference_available": True,
            "detected": bool(signals),
            "signals": signals,
            "deltas": {
                "quality_score_drop": round(quality_drop, 4),
                "low_quality_rate": round(low_quality_delta, 4),
                "failure_rate": round(failure_delta, 4),
                "tool_distribution": round(tool_delta, 4),
                "p95_latency_ms": round(latency_delta, 3),
                "p95_latency_ratio": round(latency_ratio, 4),
            },
        }


class ContinuousEvolutionRepository:
    """Persist cycles, assessments, and one resumable ingestion cursor."""

    def __init__(self, *, store: ControlPlaneStore | None = None) -> None:
        self.store = store
        self._lease_owner = f"continuous-evolution-{uuid.uuid4().hex}"
        self._cycles: OrderedDict[str, ContinuousEvolutionCycle] = OrderedDict()
        self._assessments: OrderedDict[str, TraceQualityAssessment] = OrderedDict()
        self._state = _empty_state()
        self._state_version = 0
        self._lock = threading.RLock()

    @contextmanager
    def cycle_lease(self) -> Iterator[None]:
        if not self.store:
            with self._lock:
                yield
            return
        with self.store.lease(
            "continuous-evolution-cycle", self._lease_owner, ttl_seconds=300.0
        ):
            yield

    def state(self) -> dict[str, Any]:
        if self.store:
            stored = self.store.get(CONTINUOUS_STATE_NAMESPACE, CONTINUOUS_STATE_ID)
            if stored:
                self._state_version = stored.version
                return deepcopy(stored.payload)
        with self._lock:
            return deepcopy(self._state)

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.store:
            stored = self.store.upsert(
                CONTINUOUS_STATE_NAMESPACE,
                CONTINUOUS_STATE_ID,
                state,
                expected_version=self._state_version,
            )
            self._state_version = stored.version
        with self._lock:
            self._state = deepcopy(state)
            return deepcopy(state)

    def save_assessment(self, item: TraceQualityAssessment) -> TraceQualityAssessment:
        if self.store:
            self.store.upsert(
                CONTINUOUS_ASSESSMENT_NAMESPACE,
                item.assessment_id,
                item.to_dict(),
            )
        with self._lock:
            self._assessments[item.assessment_id] = deepcopy(item)
            return deepcopy(item)

    def save_cycle(self, item: ContinuousEvolutionCycle) -> ContinuousEvolutionCycle:
        if self.store:
            self.store.upsert(CONTINUOUS_CYCLE_NAMESPACE, item.cycle_id, item.to_dict())
        with self._lock:
            self._cycles[item.cycle_id] = deepcopy(item)
            return deepcopy(item)

    def assessments(self) -> list[TraceQualityAssessment]:
        if self.store:
            return [
                TraceQualityAssessment(**item.payload)
                for item in self.store.list(CONTINUOUS_ASSESSMENT_NAMESPACE)
            ]
        with self._lock:
            return deepcopy(list(self._assessments.values()))

    def cycles(self) -> list[ContinuousEvolutionCycle]:
        if self.store:
            return [
                ContinuousEvolutionCycle(**item.payload)
                for item in self.store.list(CONTINUOUS_CYCLE_NAMESPACE)
            ]
        with self._lock:
            return deepcopy(list(self._cycles.values()))


class ContinuousShadowEvolutionService:
    """Consume each Trace once and stop every successful candidate at review."""

    def __init__(
        self,
        *,
        traces: TraceRepository,
        feedback: FeedbackRepository,
        evolution: EvolutionRepository,
        repository: ContinuousEvolutionRepository,
        minimum_cluster_support: int = 2,
        default_batch_size: int = 100,
    ) -> None:
        self.traces = traces
        self.feedback = feedback
        self.evolution = evolution
        self.repository = repository
        self.minimum_cluster_support = minimum_cluster_support
        self.default_batch_size = default_batch_size
        self.scorer = TraceQualityScorer()
        self.detector = TraceDriftDetector()
        self.factory = EvolutionCandidateFactory()
        self.evaluator = ShadowEvaluator()

    def scan(self, *, batch_size: int | None = None) -> dict[str, Any]:
        limit = batch_size or self.default_batch_size
        if limit < 1 or limit > 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        with self.repository.cycle_lease():
            state = self.repository.state()
            batch = _next_batch(self.traces.list(), state.get("last_trace_id"), limit)
            if not batch:
                return {
                    "mode": "trace_driven_continuous_shadow",
                    "status": "idle",
                    "processed_trace_count": 0,
                    "cursor": state.get("last_trace_id"),
                    "automatic_activation": False,
                    "human_review_required": True,
                }
            started_at = _now()
            batch_id = f"batch_{_digest(':'.join(item['trace_id'] for item in batch))}"
            feedback_by_trace: dict[str, list[FeedbackRecord]] = defaultdict(list)
            for feedback_record in self.feedback.list():
                feedback_by_trace[feedback_record.trace_id].append(feedback_record)
            assessments = [
                self.scorer.assess(
                    trace,
                    feedback_by_trace.get(trace["trace_id"], []),
                    batch_id=batch_id,
                    assessed_at=started_at,
                )
                for trace in batch
            ]
            profile = self.detector.profile(batch, assessments)
            reference = state.get("baseline_profile")
            drift = self.detector.detect(profile, reference)
            failures = (
                _actionable_failures(batch, assessments, feedback_by_trace)
                if drift["detected"] else []
            )
            clusters = _cluster_failures(
                failures,
                batch_id=batch_id,
                minimum_support=self.minimum_cluster_support,
            )
            candidate_ids = self._evaluate_candidates(failures, clusters, started_at)
            gates = {
                "batch_bounded": len(batch) <= limit,
                "cursor_advanced": batch[-1]["trace_id"] != state.get("last_trace_id"),
                "all_traces_assessed": len(assessments) == len(batch),
                "only_actionable_failures_proposed": len(failures)
                == sum(item.actionable for item in assessments),
                "automatic_activation_blocked": True,
                "human_review_required": True,
            }
            status = (
                "pending_review"
                if candidate_ids
                else "drift_observed" if drift["detected"] else "healthy"
            )
            completed_at = _now()
            cursor_before = state.get("last_trace_id")
            cycle_key = f"{batch_id}:{cursor_before or 'stream_start'}"
            cycle = ContinuousEvolutionCycle(
                cycle_id=f"cycle_{_digest(cycle_key)}",
                schema_version="continuous-evolution-cycle-v1",
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                cursor_before=cursor_before,
                cursor_after=batch[-1]["trace_id"],
                trace_count=len(batch),
                low_quality_count=sum(item.low_quality for item in assessments),
                actionable_count=sum(item.actionable for item in assessments),
                profile=profile,
                drift=drift,
                candidate_ids=candidate_ids,
                gates=gates,
            )
            for assessment in assessments:
                self.repository.save_assessment(assessment)
            self.repository.save_cycle(cycle)
            next_state = {
                "schema_version": "continuous-evolution-state-v1",
                "last_trace_id": batch[-1]["trace_id"],
                "processed_trace_count": state.get("processed_trace_count", 0) + len(batch),
                "baseline_profile": profile if not drift["detected"] else reference,
                "last_cycle_id": cycle.cycle_id,
                "updated_at": completed_at,
                "automatic_activation": False,
                "human_review_required": True,
            }
            self.repository.save_state(next_state)
            return cycle.to_dict()

    def state(self) -> dict[str, Any]:
        state = self.repository.state()
        return {
            "mode": "trace_driven_continuous_shadow",
            **state,
            "cycle_count": len(self.repository.cycles()),
            "assessment_count": len(self.repository.assessments()),
            "cycles": [item.to_dict() for item in self.repository.cycles()],
        }

    def _evaluate_candidates(
        self,
        failures: list[MinedFailure],
        clusters: list[FailureCluster],
        created_at: str,
    ) -> list[str]:
        candidate_ids = []
        for failure in failures:
            self.evolution.save_failure(failure)
        for cluster in clusters:
            self.evolution.save_cluster(cluster)
            candidate = self.factory.build(cluster, created_at=created_at)
            candidate.status = "shadow_evaluating"
            candidate.shadow_evaluation = self.evaluator.evaluate(candidate, failures)
            candidate.status = candidate.shadow_evaluation["next_status"]
            candidate.active = False
            self.evolution.save_candidate(candidate)
            candidate_ids.append(candidate.candidate_id)
        return candidate_ids


def _next_batch(
    traces: list[dict[str, Any]],
    cursor: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if cursor is None:
        return traces[:limit]
    positions = [index for index, item in enumerate(traces) if item.get("trace_id") == cursor]
    if not positions:
        raise ValueError("Continuous evolution cursor does not exist in Trace storage.")
    return traces[positions[0] + 1:positions[0] + 1 + limit]


def _actionable_failures(
    traces: list[dict[str, Any]],
    assessments: list[TraceQualityAssessment],
    feedback_by_trace: dict[str, list[FeedbackRecord]],
) -> list[MinedFailure]:
    trace_by_id = {item["trace_id"]: item for item in traces}
    failures = []
    for assessment in assessments:
        if not assessment.actionable or not assessment.expected_tool:
            continue
        trace = trace_by_id[assessment.trace_id]
        matching = [
            item
            for item in feedback_by_trace.get(assessment.trace_id, [])
            if item.rating == -1
            and item.issue_type == "wrong_tool"
            and item.expected_tool == assessment.expected_tool
        ]
        if not matching:
            continue
        classification = matching[0].observed.get("classification", {})
        trigger = classification.get("trigger")
        if not trigger:
            continue
        cluster_key = f"trace-router:{assessment.expected_tool}:{trigger}"
        failures.append(MinedFailure(
            failure_id=f"failure_{_digest(f'{assessment.trace_id}:{cluster_key}')}",
            source="trace_stream",
            case_id=assessment.trace_id,
            query=trace["input"]["resolved_query"],
            issue_type="router_miss",
            cluster_key=cluster_key,
            expected={"tool": assessment.expected_tool, "answer_contains": []},
            observed={
                "tool": trace["plan"]["tool"],
                "execution_status": trace["output"]["execution_status"],
                "trace_id": assessment.trace_id,
                "quality_score": assessment.quality_score,
            },
            candidate_signal={"trigger": trigger, "tool": assessment.expected_tool},
        ))
    return failures


def _cluster_failures(
    failures: list[MinedFailure],
    *,
    batch_id: str,
    minimum_support: int,
) -> list[FailureCluster]:
    grouped: dict[str, list[MinedFailure]] = defaultdict(list)
    for failure in failures:
        grouped[failure.cluster_key].append(failure)
    clusters = []
    for key, items in sorted(grouped.items()):
        if len(items) < minimum_support:
            continue
        cluster_id = f"continuous_{_digest(f'{batch_id}:{key}')}"
        clusters.append(FailureCluster(
            cluster_id=cluster_id,
            issue_type="router_miss",
            cluster_key=key,
            failure_ids=[item.failure_id for item in items],
            support=len(items),
            candidate_asset_type="router_rule",
            signal=dict(items[0].candidate_signal),
        ))
    return clusters


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": "continuous-evolution-state-v1",
        "last_trace_id": None,
        "processed_trace_count": 0,
        "baseline_profile": None,
        "last_cycle_id": None,
        "updated_at": None,
        "automatic_activation": False,
        "human_review_required": True,
    }


def _distribution_distance(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys) / 2


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_CONTINUOUS_EVOLUTION_REPOSITORY = ContinuousEvolutionRepository(
    store=DEFAULT_CONTROL_PLANE_STORE
)
DEFAULT_CONTINUOUS_EVOLUTION_SERVICE = ContinuousShadowEvolutionService(
    traces=DEFAULT_TRACE_REPOSITORY,
    feedback=DEFAULT_FEEDBACK_REPOSITORY,
    evolution=DEFAULT_EVOLUTION_REPOSITORY,
    repository=DEFAULT_CONTINUOUS_EVOLUTION_REPOSITORY,
)
