"""Stable-hash policy assignment and configuration rule execution."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.agent.llm_router import VALID_TOOLS
from app.agent.router import extract_component, extract_package, extract_release
from app.policy.models import PolicyAssignment
from app.policy.monitor import PolicyMonitor
from app.policy.repository import DEFAULT_POLICY_PATH, PolicyRepository
from app.storage.database import DEFAULT_CONTROL_PLANE_STORE


class PolicyConfigValidator:
    def validate(self, config: dict[str, Any]) -> list[str]:
        issues = []
        allowed_keys = {"rules", "aliases", "retriever"}
        if not config or not set(config) <= allowed_keys:
            issues.append("invalid_config_keys")
        rules = config.get("rules", [])
        if not isinstance(rules, list):
            return ["rules_must_be_list"]
        for rule in rules:
            if set(rule) != {"hook_id", "match", "action", "priority"}:
                issues.append("invalid_rule_keys")
                continue
            if rule.get("match", {}).get("mode") != "any":
                issues.append("unsupported_match_mode")
            terms = rule.get("match", {}).get("terms", [])
            if not terms or not all(isinstance(term, str) and term.strip() for term in terms):
                issues.append("invalid_match_terms")
            action = rule.get("action", {})
            if action.get("tool") not in VALID_TOOLS:
                issues.append("invalid_action_tool")
            if not isinstance(action.get("intent"), str) or not action.get("intent"):
                issues.append("invalid_action_intent")
            if not isinstance(rule.get("priority"), int):
                issues.append("invalid_priority")
        aliases = config.get("aliases", {})
        if not isinstance(aliases, dict):
            issues.append("aliases_must_be_dict")
        else:
            for alias, canonical in aliases.items():
                if not isinstance(alias, str) or not alias.strip():
                    issues.append("invalid_alias")
                if not isinstance(canonical, str) or not canonical.strip():
                    issues.append("invalid_canonical_alias")
        retriever = config.get("retriever")
        if retriever is not None:
            if not isinstance(retriever, dict) or set(retriever) != {
                "mode", "rrf_weight", "reranker_weight"
            }:
                issues.append("invalid_retriever_config")
            else:
                if retriever.get("mode") != "hybrid":
                    issues.append("invalid_retriever_mode")
                for key in ("rrf_weight", "reranker_weight"):
                    value = retriever.get(key)
                    if not isinstance(value, (int, float)) or not 0 <= value <= 1000:
                        issues.append(f"invalid_retriever_{key}")
        return sorted(set(issues))


class PolicyEngine:
    def __init__(
        self,
        repository: PolicyRepository,
        monitor: PolicyMonitor | None = None,
        *,
        hash_salt: str = "software-agent-policy-v1",
    ) -> None:
        self.repository = repository
        self.monitor = monitor or PolicyMonitor()
        self.hash_salt = hash_salt

    def assign(self, session_id: str) -> PolicyAssignment:
        stable = self.repository.stable()
        rollout = self.repository.rollout()
        bucket = self.bucket(session_id)
        selected = stable
        cohort = "control"
        percentage = 0.0
        if rollout:
            percentage = rollout.rollout_percentage
            if bucket < percentage:
                selected = rollout
                cohort = "rollout"
        return PolicyAssignment(
            policy_id=selected.policy_id,
            version=selected.version,
            cohort=cohort,
            bucket=bucket,
            rollout_percentage=percentage,
            config=selected.config,
        )

    def bucket(self, session_id: str) -> float:
        digest = hashlib.sha256(f"{self.hash_salt}:{session_id}".encode()).hexdigest()
        return (int(digest[:12], 16) % 10000) / 100.0

    def rewrite_query(
        self,
        query: str,
        assignment: PolicyAssignment,
    ) -> tuple[str, dict[str, Any]]:
        rewritten = query
        applied = []
        aliases = assignment.config.get("aliases", {})
        for alias in sorted(aliases, key=len, reverse=True):
            canonical = aliases[alias]
            pattern = re.compile(re.escape(alias), re.IGNORECASE)
            rewritten, count = pattern.subn(canonical, rewritten)
            if count:
                applied.append({"alias": alias, "canonical": canonical, "count": count})
        return rewritten, {
            "schema_version": "policy-query-transform-v1",
            "applied_aliases": applied,
            "changed": rewritten != query,
        }

    @staticmethod
    def retriever_options(assignment: PolicyAssignment) -> dict[str, Any] | None:
        retriever = assignment.config.get("retriever")
        return dict(retriever) if isinstance(retriever, dict) else None

    def plan_for_query(
        self,
        query: str,
        assignment: PolicyAssignment,
    ) -> dict[str, Any] | None:
        lowered = query.lower()
        for rule in sorted(
            assignment.config.get("rules", []),
            key=lambda item: item.get("priority", 0),
            reverse=True,
        ):
            terms = [term.lower() for term in rule["match"]["terms"]]
            if not any(term in lowered for term in terms):
                continue
            action = rule["action"]
            arguments = {
                "package": extract_package(lowered),
                "release": extract_release(lowered),
                "component": extract_component(lowered),
                "query": query,
            }
            return {
                "intent": action["intent"],
                "tool": action["tool"],
                "arguments": arguments,
                "confidence": "high",
                "reason": f"Matched versioned policy rule {rule['hook_id']}.",
                "steps": [{
                    "tool": action["tool"],
                    "arguments": arguments,
                    "reason": f"Policy {assignment.policy_id} selected {action['tool']}.",
                }],
            }
        return None

    def observe(
        self,
        assignment: PolicyAssignment,
        *,
        success: bool,
        latency_ms: float,
    ) -> dict[str, Any] | None:
        self.monitor.record(
            assignment.policy_id,
            success=success,
            latency_ms=latency_ms,
        )
        return self.monitor.evaluate(self.repository)


DEFAULT_POLICY_REPOSITORY = PolicyRepository(
    path=None if DEFAULT_CONTROL_PLANE_STORE else DEFAULT_POLICY_PATH,
    store=DEFAULT_CONTROL_PLANE_STORE,
)
DEFAULT_POLICY_MONITOR = PolicyMonitor()
DEFAULT_POLICY_ENGINE = PolicyEngine(DEFAULT_POLICY_REPOSITORY, DEFAULT_POLICY_MONITOR)
