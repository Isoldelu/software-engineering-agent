"""Bounded repositories for Feedback and policy candidates."""

from __future__ import annotations

import threading
from collections import OrderedDict
from copy import deepcopy

from app.feedback.models import FeedbackRecord, PolicyCandidate
from app.storage.database import DEFAULT_CONTROL_PLANE_STORE, ControlPlaneStore


class FeedbackRepository:
    def __init__(
        self,
        *,
        max_records: int = 1000,
        store: ControlPlaneStore | None = None,
    ) -> None:
        self.max_records = max_records
        self.store = store
        self._records: OrderedDict[str, FeedbackRecord] = OrderedDict()
        self._versions: dict[str, int] = {}
        self._lock = threading.RLock()

    def save(self, record: FeedbackRecord) -> FeedbackRecord:
        if self.store:
            stored = self.store.upsert(
                "feedback",
                record.feedback_id,
                record.to_dict(),
                expected_version=self._versions.get(record.feedback_id, 0),
            )
            self._versions[record.feedback_id] = stored.version
        with self._lock:
            self._records.pop(record.feedback_id, None)
            self._records[record.feedback_id] = deepcopy(record)
            while len(self._records) > self.max_records:
                self._records.popitem(last=False)
            return deepcopy(record)

    def get(self, feedback_id: str) -> FeedbackRecord | None:
        if self.store:
            stored = self.store.get("feedback", feedback_id)
            if not stored:
                return None
            self._versions[feedback_id] = stored.version
            return FeedbackRecord(**stored.payload)
        with self._lock:
            record = self._records.get(feedback_id)
            return deepcopy(record) if record else None

    def list(self, *, fingerprint: str | None = None) -> list[FeedbackRecord]:
        if self.store:
            stored = self.store.list("feedback")
            self._versions.update({item.record_id: item.version for item in stored})
            records = [FeedbackRecord(**item.payload) for item in stored]
            if fingerprint:
                records = [item for item in records if item.fingerprint == fingerprint]
            return records
        with self._lock:
            records = list(self._records.values())
            if fingerprint:
                records = [item for item in records if item.fingerprint == fingerprint]
            return deepcopy(records)

    def count(self) -> int:
        if self.store:
            return self.store.count("feedback")
        with self._lock:
            return len(self._records)


class CandidateRepository:
    def __init__(
        self,
        *,
        max_records: int = 200,
        store: ControlPlaneStore | None = None,
    ) -> None:
        self.max_records = max_records
        self.store = store
        self._records: OrderedDict[str, PolicyCandidate] = OrderedDict()
        self._versions: dict[str, int] = {}
        self._lock = threading.RLock()

    def save(self, candidate: PolicyCandidate) -> PolicyCandidate:
        if self.store:
            stored = self.store.upsert(
                "policy_candidate",
                candidate.candidate_id,
                candidate.to_dict(),
                expected_version=self._versions.get(candidate.candidate_id, 0),
            )
            self._versions[candidate.candidate_id] = stored.version
        with self._lock:
            self._records.pop(candidate.candidate_id, None)
            self._records[candidate.candidate_id] = deepcopy(candidate)
            while len(self._records) > self.max_records:
                self._records.popitem(last=False)
            return deepcopy(candidate)

    def get(self, candidate_id: str) -> PolicyCandidate | None:
        if self.store:
            stored = self.store.get("policy_candidate", candidate_id)
            if not stored:
                return None
            self._versions[candidate_id] = stored.version
            return PolicyCandidate(**stored.payload)
        with self._lock:
            candidate = self._records.get(candidate_id)
            return deepcopy(candidate) if candidate else None

    def list(self) -> list[PolicyCandidate]:
        if self.store:
            stored = self.store.list("policy_candidate")
            self._versions.update({item.record_id: item.version for item in stored})
            return [PolicyCandidate(**item.payload) for item in stored]
        with self._lock:
            return deepcopy(list(self._records.values()))


DEFAULT_FEEDBACK_REPOSITORY = FeedbackRepository(store=DEFAULT_CONTROL_PLANE_STORE)
DEFAULT_CANDIDATE_REPOSITORY = CandidateRepository(store=DEFAULT_CONTROL_PLANE_STORE)
