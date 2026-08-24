"""Trace-backed Feedback observation and deterministic bad-case classification."""

from __future__ import annotations

import re
from typing import Any

from app.agent.router import PACKAGE_NAMES
from app.agent.trace import TraceRepository
from app.feedback.models import VALID_ISSUE_TYPES


GENERIC_TERMS = {
    "a", "an", "the", "what", "which", "query", "package", "info",
    "please", "show", "check", "for", "of", "is", "are",
}


class FeedbackObserver:
    def __init__(self, traces: TraceRepository) -> None:
        self.traces = traces

    def observe(self, trace_id: str) -> dict[str, Any]:
        trace = self.traces.get(trace_id)
        if not trace:
            raise KeyError(f"Trace not found: {trace_id}")
        return {
            "trace_id": trace_id,
            "session_id": trace.get("session_id"),
            "policy_version": trace.get("policy_version"),
            "original_query": trace["input"]["original_query"],
            "resolved_query": trace["input"]["resolved_query"],
            "selected_tool": trace["plan"]["tool"],
            "intent": trace["plan"]["intent"],
            "execution_status": trace["output"]["execution_status"],
            "verification": trace["output"].get("verification", {}),
            "tool_statuses": [step.get("status") for step in trace.get("steps", [])],
            "evidence_ids": trace["output"].get("evidence_ids", []),
        }


class BadCaseClassifier:
    def classify(
        self,
        observed: dict[str, Any],
        *,
        expected_tool: str | None = None,
        issue_type: str | None = None,
    ) -> dict[str, Any]:
        if issue_type and issue_type not in VALID_ISSUE_TYPES:
            raise ValueError(f"Unsupported issue type: {issue_type}")
        inferred = issue_type or self._infer(observed, expected_tool)
        trigger = _extract_trigger(observed["resolved_query"])
        fingerprint = f"{inferred}:{expected_tool or 'none'}:{trigger or 'none'}"
        return {
            "issue_type": inferred,
            "trigger": trigger,
            "fingerprint": fingerprint,
            "attribution": {
                "layer": _attribution_layer(inferred),
                "selected_tool": observed["selected_tool"],
                "expected_tool": expected_tool,
                "policy_version": observed["policy_version"],
            },
        }

    @staticmethod
    def _infer(observed: dict[str, Any], expected_tool: str | None) -> str:
        if expected_tool and observed["selected_tool"] != expected_tool:
            return "wrong_tool"
        if observed["execution_status"] == "failed" or "failed" in observed["tool_statuses"]:
            return "tool_execution_failed"
        if not observed.get("evidence_ids"):
            return "answer_not_grounded"
        if not observed.get("verification", {}).get("passed", True):
            return "verification_failed"
        return "answer_incomplete"


def _extract_trigger(query: str) -> str | None:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", query.lower())
    candidates = [
        token for token in tokens
        if token not in GENERIC_TERMS and token not in PACKAGE_NAMES
    ]
    return candidates[-1] if candidates else None


def _attribution_layer(issue_type: str) -> str:
    return {
        "wrong_tool": "router",
        "tool_execution_failed": "tool",
        "answer_not_grounded": "answer",
        "answer_incomplete": "answer",
        "verification_failed": "verifier",
    }[issue_type]
