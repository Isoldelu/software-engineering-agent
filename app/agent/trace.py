"""Privacy-bounded enhanced Trace recording and deterministic replay."""

from __future__ import annotations

import json
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.storage.database import DEFAULT_CONTROL_PLANE_STORE, ControlPlaneStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "data" / "traces.jsonl"
TRACE_SCHEMA_VERSION = "trace-v1"


class TraceRepository:
    """Bounded in-memory Trace storage with optional append-only JSONL persistence."""

    def __init__(
        self,
        *,
        path: str | Path = DEFAULT_TRACE_PATH,
        max_records: int = 1000,
        store: ControlPlaneStore | None = None,
    ) -> None:
        self.path = Path(path)
        self.max_records = max_records
        self.store = store
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def new_trace_id(self) -> str:
        return f"tr_{uuid.uuid4().hex[:20]}"

    def save(self, trace: dict[str, Any], *, persist: bool = False) -> dict[str, Any]:
        with self._lock:
            trace_id = trace["trace_id"]
            self._records.pop(trace_id, None)
            self._records[trace_id] = deepcopy(trace)
            while len(self._records) > self.max_records:
                self._records.popitem(last=False)
        persistence = {"recorded": False, "path": str(self.path)}
        if self.store:
            stored = self.store.upsert("trace", trace_id, trace)
            persistence = {
                "recorded": True,
                "backend": self.store.scheme,
                "namespace": "trace",
                "version": stored.version,
            }
        if persist:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(trace, ensure_ascii=False) + "\n")
                persistence["recorded"] = True
            except OSError as exc:
                persistence["error"] = str(exc)
        return persistence

    def get(self, trace_id: str) -> dict[str, Any] | None:
        if self.store:
            stored = self.store.get("trace", trace_id)
            return deepcopy(stored.payload) if stored else None
        with self._lock:
            trace = self._records.get(trace_id)
            return deepcopy(trace) if trace else self._read_persisted(trace_id)

    def count(self) -> int:
        if self.store:
            return self.store.count("trace")
        with self._lock:
            return len(self._records)

    def _read_persisted(self, trace_id: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if record.get("trace_id") == trace_id:
                    return record
        except (OSError, json.JSONDecodeError):
            return None
        return None


class TraceRecorder:
    def build(
        self,
        *,
        trace_id: str,
        session_id: str,
        parent_trace_id: str | None,
        original_query: str,
        resolved_query: str,
        inherited_entities: dict[str, Any],
        plan: dict[str, Any],
        observations: list[dict[str, Any]],
        result: dict[str, Any],
        started_at: str,
        total_latency_ms: float,
    ) -> dict[str, Any]:
        steps = []
        for index, item in enumerate(observations, start=1):
            observation = item["observation"]
            steps.append({
                "step": index,
                "tool": item["tool"],
                "input": observation.get("query", resolved_query),
                "status": observation.get("status"),
                "latency_ms": observation.get("metadata", {}).get("latency_ms", 0.0),
                "evidence_ids": [
                    evidence["evidence_id"]
                    for evidence in observation.get("evidence_items", [])
                ],
                "error": observation.get("error"),
            })
        return {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": trace_id,
            "session_id": session_id,
            "parent_trace_id": parent_trace_id,
            "created_at": started_at,
            "policy_version": result.get("policy_version"),
            "policy_assignment": result.get("policy_assignment", {}),
            "provider": result.get("provider", {}),
            "input": {
                "original_query": original_query,
                "resolved_query": resolved_query,
                "inherited_entities": inherited_entities,
            },
            "plan": {
                "intent": plan.get("intent"),
                "tool": plan.get("tool"),
                "arguments": plan.get("arguments", {}),
                "steps": plan.get("steps", []),
                "planner_source": result.get("planner_source"),
                "provider": result.get("provider", {}).get("effective_provider"),
            },
            "steps": steps,
            "output": {
                "answer": result.get("answer"),
                "execution_status": result.get("execution_status"),
                "evidence_ids": [item["evidence_id"] for item in result.get("evidence_items", [])],
                "citations": result.get("citations", []),
                "verification": result.get("verification", {}),
            },
            "metrics": {
                "total_latency_ms": round(max(0.0, total_latency_ms), 3),
                "tool_call_count": result.get("tool_call_count", 0),
                "trace_complete": True,
            },
            "privacy": {
                "stores_internal_thought": False,
                "stored_entity_types": ["package", "release", "component"],
            },
        }


class ReplayReader:
    def __init__(self, repository: TraceRepository) -> None:
        self.repository = repository

    def reconstruct(self, trace_id: str) -> dict[str, Any] | None:
        trace = self.repository.get(trace_id)
        if not trace:
            return None
        return {
            "trace_id": trace_id,
            "session_id": trace["session_id"],
            "query": trace["input"]["resolved_query"],
            "original_query": trace["input"]["original_query"],
            "inherited_entities": trace["input"].get("inherited_entities", {}),
            "policy_version": trace.get("policy_version"),
            "reconstruction_complete": all(
                key in trace for key in ("trace_id", "session_id", "input", "plan", "steps", "output")
            ),
        }

    def replay(
        self,
        trace_id: str,
        runner: Callable[..., dict[str, Any]],
    ) -> dict[str, Any] | None:
        request = self.reconstruct(trace_id)
        if not request:
            return None
        replay_result = runner(
            request["query"],
            persist_trajectory=False,
            session_id=None,
        )
        replay_result["replay_of"] = trace_id
        replay_result["replay_input"] = request
        return replay_result


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_TRACE_REPOSITORY = TraceRepository(store=DEFAULT_CONTROL_PLANE_STORE)
