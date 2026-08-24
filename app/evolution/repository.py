"""Thread-safe in-memory repositories for one offline evolution cycle."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from typing import TypeVar

from app.evolution.models import EvolutionCandidate, FailureCluster, MinedFailure
from app.storage.database import DEFAULT_CONTROL_PLANE_STORE, ControlPlaneStore

Record = TypeVar("Record", MinedFailure, FailureCluster, EvolutionCandidate)


class EvolutionRepository:
    def __init__(self, *, store: ControlPlaneStore | None = None) -> None:
        self.store = store
        self._lease_owner = f"evolution-repository-{uuid.uuid4().hex}"
        self._failures: OrderedDict[str, MinedFailure] = OrderedDict()
        self._clusters: OrderedDict[str, FailureCluster] = OrderedDict()
        self._candidates: OrderedDict[str, EvolutionCandidate] = OrderedDict()
        self._versions: dict[tuple[str, str], int] = {}
        self._lock = threading.RLock()

    def clear(self) -> None:
        if self.store:
            for namespace in ("evolution_failure", "evolution_cluster", "evolution_candidate"):
                self.store.delete_namespace(namespace)
            self._versions.clear()
        with self._lock:
            self._failures.clear()
            self._clusters.clear()
            self._candidates.clear()

    @contextmanager
    def cycle_lease(self) -> Iterator[None]:
        if not self.store:
            yield
            return
        with self.store.lease(
            "evolution-cycle",
            self._lease_owner,
            ttl_seconds=120.0,
        ):
            yield

    def save_failure(self, item: MinedFailure) -> MinedFailure:
        return self._save("evolution_failure", self._failures, item.failure_id, item)

    def save_cluster(self, item: FailureCluster) -> FailureCluster:
        return self._save("evolution_cluster", self._clusters, item.cluster_id, item)

    def save_candidate(self, item: EvolutionCandidate) -> EvolutionCandidate:
        return self._save("evolution_candidate", self._candidates, item.candidate_id, item)

    def get_candidate(self, candidate_id: str) -> EvolutionCandidate | None:
        if self.store:
            stored = self.store.get("evolution_candidate", candidate_id)
            if not stored:
                return None
            self._versions[("evolution_candidate", candidate_id)] = stored.version
            return EvolutionCandidate(**stored.payload)
        with self._lock:
            item = self._candidates.get(candidate_id)
            return deepcopy(item) if item else None

    def failures(self) -> list[MinedFailure]:
        if self.store:
            return self._list("evolution_failure", MinedFailure)
        with self._lock:
            return deepcopy(list(self._failures.values()))

    def clusters(self) -> list[FailureCluster]:
        if self.store:
            return self._list("evolution_cluster", FailureCluster)
        with self._lock:
            return deepcopy(list(self._clusters.values()))

    def candidates(self) -> list[EvolutionCandidate]:
        if self.store:
            return self._list("evolution_candidate", EvolutionCandidate)
        with self._lock:
            return deepcopy(list(self._candidates.values()))

    def _save(
        self,
        namespace: str,
        records: OrderedDict,
        key: str,
        item: Record,
    ) -> Record:
        if self.store:
            stored = self.store.upsert(
                namespace,
                key,
                item.to_dict(),
                expected_version=self._versions.get((namespace, key), 0),
            )
            self._versions[(namespace, key)] = stored.version
        with self._lock:
            records[key] = deepcopy(item)
            return deepcopy(item)

    def _list(self, namespace: str, model: type[Record]) -> list[Record]:
        if not self.store:
            return []
        stored = self.store.list(namespace)
        self._versions.update({(namespace, item.record_id): item.version for item in stored})
        return [model(**item.payload) for item in stored]


DEFAULT_EVOLUTION_REPOSITORY = EvolutionRepository(store=DEFAULT_CONTROL_PLANE_STORE)
