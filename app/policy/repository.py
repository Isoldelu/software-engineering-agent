"""Thread-safe versioned policy state with optional JSON persistence."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.policy.models import PolicyVersion
from app.storage.database import (
    ConcurrentUpdateError,
    ControlPlaneStore,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = Path(
    os.getenv(
        "SOFTWARE_AGENT_POLICY_STATE_PATH",
        str(PROJECT_ROOT / "data" / "policy_state.json"),
    )
)
BASE_POLICY_ID = "deterministic-policy-v1"


class PolicyRepository:
    def __init__(
        self,
        *,
        path: str | Path | None = None,
        store: ControlPlaneStore | None = None,
    ) -> None:
        self.path = Path(path) if path else None
        self.store = store
        self._store_version = 0
        self._lease_owner = f"policy-repository-{uuid.uuid4().hex}"
        self._lock = threading.RLock()
        self._policies: dict[str, PolicyVersion] = {}
        self.stable_policy_id = BASE_POLICY_ID
        self.rollout_policy_id: str | None = None
        self.last_rollback: dict[str, Any] | None = None
        stored = self.store.get("policy_state", "singleton") if self.store else None
        if stored:
            self._store_version = stored.version
            self._load_document(stored.payload)
        elif self.path and self.path.exists():
            self._load()
        else:
            self._initialize_base()
            if self.store:
                try:
                    self._persist()
                except ConcurrentUpdateError:
                    self._refresh_from_store()

    def create(
        self,
        *,
        config: dict[str, Any],
        source_candidate_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyVersion:
        with self._write_guard():
            version = max(item.version for item in self._policies.values()) + 1
            policy = PolicyVersion(
                policy_id=f"policy_v{version}",
                version=version,
                status="draft",
                config=deepcopy(config),
                rollout_percentage=0.0,
                parent_policy_id=self.stable_policy_id,
                source_candidate_id=source_candidate_id,
                created_at=_now(),
                metadata=metadata or {},
            )
            self._policies[policy.policy_id] = policy
            self._persist()
            return deepcopy(policy)

    def create_rollout_once(
        self,
        *,
        config: dict[str, Any],
        source_candidate_id: str,
        rollout_percentage: float,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[PolicyVersion, bool]:
        """Atomically create one rollout policy for a stable source id."""
        with self._write_guard():
            if not 0 < rollout_percentage <= 100:
                raise ValueError("rollout percentage must be within (0, 100]")
            existing = next(
                (
                    item
                    for item in self._policies.values()
                    if item.source_candidate_id == source_candidate_id
                ),
                None,
            )
            if existing:
                if existing.config != config:
                    raise ValueError("Existing source policy has a different configuration.")
                initial_percentage = existing.metadata.get(
                    "initial_rollout_percentage",
                    existing.rollout_percentage,
                )
                if float(initial_percentage) != float(rollout_percentage):
                    raise ValueError("Existing source policy used a different rollout percentage.")
                return deepcopy(existing), False
            if self.rollout_policy_id:
                raise ValueError("Another rollout policy is already active.")
            version = max(item.version for item in self._policies.values()) + 1
            policy_metadata = deepcopy(metadata or {})
            policy_metadata["initial_rollout_percentage"] = float(rollout_percentage)
            policy = PolicyVersion(
                policy_id=f"policy_v{version}",
                version=version,
                status="rollout",
                config=deepcopy(config),
                rollout_percentage=float(rollout_percentage),
                parent_policy_id=self.stable_policy_id,
                source_candidate_id=source_candidate_id,
                created_at=_now(),
                activated_at=_now(),
                metadata=policy_metadata,
            )
            self._policies[policy.policy_id] = policy
            self.rollout_policy_id = policy.policy_id
            self._persist()
            return deepcopy(policy), True

    def start_rollout(self, policy_id: str, percentage: float) -> PolicyVersion:
        with self._write_guard():
            if not 0 < percentage <= 100:
                raise ValueError("rollout percentage must be within (0, 100]")
            policy = self._require(policy_id)
            if policy.status not in {"draft", "rollout"}:
                raise ValueError(f"Cannot start rollout from status {policy.status}.")
            if self.rollout_policy_id and self.rollout_policy_id != policy_id:
                raise ValueError("Another rollout policy is already active.")
            policy.status = "rollout"
            policy.rollout_percentage = float(percentage)
            policy.activated_at = policy.activated_at or _now()
            policy.parent_policy_id = self.stable_policy_id
            self.rollout_policy_id = policy_id
            self._persist()
            return deepcopy(policy)

    def set_rollout_percentage(self, policy_id: str, percentage: float) -> PolicyVersion:
        with self._write_guard():
            if self.rollout_policy_id != policy_id:
                raise ValueError("Policy is not the current rollout policy.")
            if not 0 < percentage <= 100:
                raise ValueError("rollout percentage must be within (0, 100]")
            policy = self._require(policy_id)
            policy.rollout_percentage = float(percentage)
            self._persist()
            return deepcopy(policy)

    def promote(self, policy_id: str) -> PolicyVersion:
        with self._write_guard():
            if self.rollout_policy_id != policy_id:
                raise ValueError("Only the current rollout policy can be promoted.")
            previous = self._require(self.stable_policy_id)
            previous.status = "deprecated"
            previous.deprecated_at = _now()
            policy = self._require(policy_id)
            policy.status = "active"
            policy.rollout_percentage = 100.0
            self.stable_policy_id = policy_id
            self.rollout_policy_id = None
            self._persist()
            return deepcopy(policy)

    def rollback(self, policy_id: str, *, reason: str) -> PolicyVersion:
        with self._write_guard():
            policy = self._require(policy_id)
            if policy_id == self.rollout_policy_id:
                self.rollout_policy_id = None
            elif policy_id == self.stable_policy_id:
                parent_id = policy.parent_policy_id
                if not parent_id or parent_id not in self._policies:
                    raise ValueError("Stable policy has no rollback parent.")
                parent = self._require(parent_id)
                parent.status = "active"
                parent.deprecated_at = None
                parent.rollout_percentage = 100.0
                self.stable_policy_id = parent_id
            else:
                raise ValueError("Policy is neither stable nor rollout and cannot be rolled back.")
            policy.status = "rolled_back"
            policy.rollout_percentage = 0.0
            policy.rolled_back_at = _now()
            self.last_rollback = {
                "policy_id": policy_id,
                "restored_policy_id": self.stable_policy_id,
                "reason": reason,
                "timestamp": _now(),
            }
            self._persist()
            return deepcopy(policy)

    def deprecate(self, policy_id: str) -> PolicyVersion:
        with self._write_guard():
            if policy_id in {self.stable_policy_id, self.rollout_policy_id}:
                raise ValueError("Stable or rollout policy cannot be deprecated directly.")
            policy = self._require(policy_id)
            policy.status = "deprecated"
            policy.deprecated_at = _now()
            self._persist()
            return deepcopy(policy)

    def get(self, policy_id: str) -> PolicyVersion | None:
        with self._lock:
            self._refresh_from_store()
            policy = self._policies.get(policy_id)
            return deepcopy(policy) if policy else None

    def stable(self) -> PolicyVersion:
        self._refresh_from_store()
        return self._copy_required(self.stable_policy_id)

    def rollout(self) -> PolicyVersion | None:
        self._refresh_from_store()
        return self._copy_required(self.rollout_policy_id) if self.rollout_policy_id else None

    def list(self) -> list[PolicyVersion]:
        with self._lock:
            self._refresh_from_store()
            return deepcopy(sorted(self._policies.values(), key=lambda item: item.version))

    def state(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_from_store()
            return self._state_document()

    def _initialize_base(self) -> None:
        base = PolicyVersion(
            policy_id=BASE_POLICY_ID,
            version=1,
            status="active",
            config={"rules": []},
            rollout_percentage=100.0,
            parent_policy_id=None,
            source_candidate_id=None,
            created_at=_now(),
            activated_at=_now(),
            metadata={"description": "Step 17-22 deterministic baseline policy"},
        )
        self._policies = {base.policy_id: base}

    def _require(self, policy_id: str) -> PolicyVersion:
        policy = self._policies.get(policy_id)
        if not policy:
            raise KeyError(f"Policy not found: {policy_id}")
        return policy

    def _copy_required(self, policy_id: str | None) -> PolicyVersion:
        if not policy_id:
            raise KeyError("Policy id is missing.")
        with self._lock:
            return deepcopy(self._require(policy_id))

    def _persist(self) -> None:
        document = self._state_document()
        if self.store:
            stored = self.store.upsert(
                "policy_state",
                "singleton",
                document,
                expected_version=self._store_version,
            )
            self._store_version = stored.version
            return
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _load(self) -> None:
        if self.path is None:
            raise RuntimeError("A repository path is required to load policy state.")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self._load_document(document)

    def _load_document(self, document: dict[str, Any]) -> None:
        self.stable_policy_id = document["stable_policy_id"]
        self.rollout_policy_id = document.get("rollout_policy_id")
        self.last_rollback = document.get("last_rollback")
        self._policies = {
            item["policy_id"]: PolicyVersion(**item)
            for item in document["policies"]
        }

    def _state_document(self) -> dict[str, Any]:
        return {
            "schema_version": "policy-state-v1",
            "stable_policy_id": self.stable_policy_id,
            "rollout_policy_id": self.rollout_policy_id,
            "last_rollback": deepcopy(self.last_rollback),
            "policies": [
                item.to_dict()
                for item in sorted(self._policies.values(), key=lambda policy: policy.version)
            ],
        }

    def _refresh_from_store(self) -> None:
        if not self.store:
            return
        stored = self.store.get("policy_state", "singleton")
        if stored and stored.version != self._store_version:
            self._store_version = stored.version
            self._load_document(stored.payload)

    @contextmanager
    def _write_guard(self) -> Iterator[None]:
        with self._lock:
            if not self.store:
                yield
                return
            with self.store.lease(
                "policy-state-write",
                self._lease_owner,
                ttl_seconds=30.0,
                wait_timeout=3.0,
            ):
                self._refresh_from_store()
                yield


def _now() -> str:
    return datetime.now(UTC).isoformat()
