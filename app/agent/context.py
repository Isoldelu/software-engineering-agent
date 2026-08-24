"""Session-scoped task context for deterministic multi-turn Agent queries."""

from __future__ import annotations

import re
import threading
import uuid
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agent.router import extract_component, extract_package, extract_release
from app.storage.database import (
    DEFAULT_CONTROL_PLANE_STORE,
    ConcurrentUpdateError,
    ControlPlaneStore,
)

POLICY_VERSION = "deterministic-policy-v1"
PACKAGE_REFERENCES = ("它", "这个包", "该包", "this package", "that package", " it ")
FOLLOW_UP_MARKERS = (
    "依赖", "dependency", "dependencies", "版本", "version", "比较", "compare",
    "组件", "component", "文件", "file",
)


@dataclass
class AgentContext:
    session_id: str
    turn_count: int = 0
    packages: list[str] = field(default_factory=list)
    release: str | None = None
    component: str | None = None
    last_intent: str | None = None
    last_tool: str | None = None
    last_trace_id: str | None = None
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    @property
    def active_package(self) -> str | None:
        return self.packages[-1] if self.packages else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionRepository:
    """Thread-safe session repository with optional shared database state."""

    def __init__(
        self,
        *,
        max_sessions: int = 100,
        max_turns: int = 20,
        store: ControlPlaneStore | None = None,
    ) -> None:
        self.max_sessions = max_sessions
        self.max_turns = max_turns
        self.store = store
        self._sessions: OrderedDict[str, AgentContext] = OrderedDict()
        self._versions: dict[str, int] = {}
        self._lock = threading.RLock()

    def create_session_id(self) -> str:
        return f"ses_{uuid.uuid4().hex[:16]}"

    def get_or_create(self, session_id: str | None = None) -> AgentContext:
        if self.store:
            key = session_id or self.create_session_id()
            stored = self.store.get("session", key)
            if stored:
                self._versions[key] = stored.version
                return AgentContext(**stored.payload)
            context = AgentContext(session_id=key)
            try:
                created = self.store.upsert(
                    "session", key, context.to_dict(), expected_version=0
                )
            except ConcurrentUpdateError:
                recovered = self.store.get("session", key)
                if not recovered:
                    raise
                context = AgentContext(**recovered.payload)
                created = recovered
            self._versions[key] = created.version
            return deepcopy(context)
        with self._lock:
            key = session_id or self.create_session_id()
            if key in self._sessions:
                context = self._sessions.pop(key)
                self._sessions[key] = context
                return deepcopy(context)
            context = AgentContext(session_id=key)
            self._sessions[key] = context
            self._evict_if_needed()
            return deepcopy(context)

    def get(self, session_id: str) -> AgentContext | None:
        if self.store:
            stored = self.store.get("session", session_id)
            if not stored:
                return None
            self._versions[session_id] = stored.version
            return AgentContext(**stored.payload)
        with self._lock:
            context = self._sessions.get(session_id)
            return deepcopy(context) if context else None

    def save(self, context: AgentContext) -> AgentContext:
        context.updated_at = _now()
        context.recent_turns = context.recent_turns[-self.max_turns:]
        if self.store:
            stored = self.store.upsert(
                "session",
                context.session_id,
                context.to_dict(),
                expected_version=self._versions.get(context.session_id, 0),
            )
            self._versions[context.session_id] = stored.version
            return deepcopy(context)
        with self._lock:
            self._sessions.pop(context.session_id, None)
            self._sessions[context.session_id] = deepcopy(context)
            self._evict_if_needed()
            return deepcopy(context)

    def clear(self, session_id: str) -> bool:
        if self.store:
            stored = self.store.get("session", session_id)
            if not stored:
                return False
            deleted = self.store.delete(
                "session", session_id, expected_version=stored.version
            )
            self._versions.pop(session_id, None)
            return deleted
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def clear_all(self) -> None:
        if self.store:
            self.store.delete_namespace("session")
            self._versions.clear()
            return
        with self._lock:
            self._sessions.clear()

    def count(self) -> int:
        if self.store:
            return self.store.count("session")
        with self._lock:
            return len(self._sessions)

    def _evict_if_needed(self) -> None:
        while len(self._sessions) > self.max_sessions:
            self._sessions.popitem(last=False)


class ContextResolver:
    """Resolve explicit pronouns and omitted entities using task-only context."""

    def resolve(self, query: str, context: AgentContext) -> tuple[str, dict[str, Any]]:
        normalized = query.lower()
        explicit_package = extract_package(normalized)
        explicit_release = extract_release(normalized)
        explicit_component = extract_component(normalized)
        inherited: dict[str, Any] = {}
        resolved = query.strip()

        package = context.active_package
        has_package_reference = any(marker in f" {normalized} " for marker in PACKAGE_REFERENCES)
        follow_up_without_entity = (
            package
            and not explicit_package
            and any(marker in normalized for marker in FOLLOW_UP_MARKERS)
            and not _references_release(normalized)
        )
        if package and (has_package_reference or follow_up_without_entity):
            resolved = _replace_package_reference(resolved, package)
            if package.lower() not in resolved.lower():
                resolved = f"{package} {resolved}"
            inherited["package"] = package

        if context.release and not explicit_release and _references_release(normalized):
            resolved = f"release {context.release} {resolved}"
            inherited["release"] = context.release
        if context.component and not explicit_component and _references_component(normalized):
            resolved = f"{context.component} {resolved}"
            inherited["component"] = context.component
        return resolved, inherited

    def update(
        self,
        context: AgentContext,
        *,
        original_query: str,
        resolved_query: str,
        plan: dict[str, Any],
        observations: list[dict[str, Any]],
        trace_id: str,
        execution_status: str,
    ) -> AgentContext:
        normalized = resolved_query.lower()
        packages = _packages_from_execution(plan, observations)
        explicit_package = extract_package(normalized)
        if explicit_package:
            packages.append(explicit_package)
        for package in packages:
            if package and package not in context.packages:
                context.packages.append(package)
        if explicit_package:
            context.packages = [
                package for package in context.packages if package != explicit_package
            ] + [explicit_package]
        context.packages = context.packages[-8:]
        context.release = extract_release(normalized) or plan.get("arguments", {}).get("release") or context.release
        context.component = extract_component(normalized) or plan.get("arguments", {}).get("component") or context.component
        context.last_intent = plan.get("intent")
        context.last_tool = plan.get("tool")
        context.last_trace_id = trace_id
        context.turn_count += 1
        context.recent_turns.append({
            "turn": context.turn_count,
            "original_query": original_query,
            "resolved_query": resolved_query,
            "intent": context.last_intent,
            "tool": context.last_tool,
            "execution_status": execution_status,
            "trace_id": trace_id,
        })
        return context


def _packages_from_execution(plan: dict, observations: list[dict]) -> list[str]:
    packages: list[str] = []
    package = plan.get("arguments", {}).get("package")
    if package:
        packages.append(package)
    for item in observations:
        observation = item.get("observation", {})
        result = observation.get("result")
        if isinstance(result, dict) and result.get("package"):
            packages.append(result["package"])
        elif isinstance(result, list):
            packages.extend(record["package"] for record in result if record.get("package"))
        packages.extend(
            owner["package"]
            for owner in observation.get("owners", [])
            if owner.get("package")
        )
        if observation.get("package"):
            packages.append(observation["package"])
    return packages


def _replace_package_reference(query: str, package: str) -> str:
    resolved = query
    for marker in PACKAGE_REFERENCES:
        resolved = re.sub(re.escape(marker.strip()), package, resolved, flags=re.IGNORECASE)
    return resolved


def _references_release(query: str) -> bool:
    return any(marker in query for marker in ("这个版本", "该版本", "this release", "that release"))


def _references_component(query: str) -> bool:
    return any(marker in query for marker in ("这个组件", "该组件", "this component", "that component"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_SESSION_REPOSITORY = SessionRepository(store=DEFAULT_CONTROL_PLANE_STORE)
