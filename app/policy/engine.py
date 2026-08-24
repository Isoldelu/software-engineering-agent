"""Stable-hash policy assignment and configuration rule execution."""

from __future__ import annotations

import hashlib
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
        if set(config) != {"rules"}:
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
