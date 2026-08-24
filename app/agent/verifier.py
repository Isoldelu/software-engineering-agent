"""Deterministic online verification for Agent answers and executions."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from app.evidence.validator import EvidenceValidator


CHECKED_RULES = [
    "plan_complete",
    "arguments_satisfied",
    "evidence_integrity",
    "citations_valid",
    "citation_coverage",
    "version_claims_grounded",
    "dependency_direction_valid",
    "execution_status_consistent",
    "not_found_semantics",
    "hybrid_completeness",
    "answer_nonempty",
]


@dataclass(frozen=True)
class VerificationIssue:
    type: str
    severity: str
    message: str
    repairable: bool
    rule: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    passed: bool
    score: float
    issues: list[dict[str, Any]]
    checked_rules: list[str] = field(default_factory=lambda: list(CHECKED_RULES))
    repair_count: int = 0
    initial_issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeterministicVerifier:
    """Verify plan execution, grounding, citations, and status before response."""

    def verify(
        self,
        *,
        plan: dict[str, Any],
        observations: list[dict[str, Any]],
        answer: str,
        evidence_items: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        execution_status: str,
    ) -> VerificationResult:
        issues_by_rule = {
            "plan_complete": self._check_plan_complete(plan, observations),
            "arguments_satisfied": self._check_arguments(plan),
            "evidence_integrity": self._check_evidence_integrity(observations),
            "citations_valid": self._check_citations_valid(evidence_items, citations),
            "citation_coverage": self._check_citation_coverage(evidence_items, citations),
            "version_claims_grounded": self._check_version_claims(answer, evidence_items),
            "dependency_direction_valid": self._check_dependency_direction(answer, evidence_items),
            "execution_status_consistent": self._check_execution_status(
                observations, execution_status
            ),
            "not_found_semantics": self._check_not_found_semantics(
                answer, evidence_items, citations, execution_status
            ),
            "hybrid_completeness": self._check_hybrid_completeness(
                plan, observations, answer
            ),
            "answer_nonempty": self._check_answer_nonempty(answer),
        }
        issues = [issue for rule_issues in issues_by_rule.values() for issue in rule_issues]
        failed_rules = sum(1 for rule_issues in issues_by_rule.values() if rule_issues)
        score = (len(CHECKED_RULES) - failed_rules) / len(CHECKED_RULES)
        return VerificationResult(
            passed=not any(issue["severity"] == "error" for issue in issues),
            score=round(score, 4),
            issues=issues,
        )

    def verify_and_repair(
        self,
        *,
        plan: dict[str, Any],
        observations: list[dict[str, Any]],
        answer: str,
        evidence_items: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        execution_status: str,
        answer_composer: Callable[[], str],
    ) -> tuple[str, VerificationResult]:
        """Allow at most one deterministic answer recomposition."""
        initial = self.verify(
            plan=plan,
            observations=observations,
            answer=answer,
            evidence_items=evidence_items,
            citations=citations,
            execution_status=execution_status,
        )
        if initial.passed or not initial.issues:
            return answer, initial
        if not all(issue["repairable"] for issue in initial.issues):
            return answer, initial

        repaired_answer = answer_composer()
        repaired = self.verify(
            plan=plan,
            observations=observations,
            answer=repaired_answer,
            evidence_items=evidence_items,
            citations=citations,
            execution_status=execution_status,
        )
        repaired.repair_count = 1
        repaired.initial_issues = initial.issues
        return repaired_answer, repaired

    @staticmethod
    def _check_plan_complete(
        plan: dict[str, Any], observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        observed_tools = {item.get("tool") for item in observations}
        missing = [
            step.get("tool") for step in plan.get("steps", [])
            if step.get("tool") not in observed_tools
        ]
        if not missing:
            return []
        return [_issue(
            "missing_tool",
            "plan_complete",
            f"Planned tools were not executed: {missing}",
            repairable=False,
        )]

    @staticmethod
    def _check_arguments(plan: dict[str, Any]) -> list[dict[str, Any]]:
        for index, step in enumerate(plan.get("steps", []), start=1):
            arguments = step.get("arguments")
            if not isinstance(arguments, dict):
                return [_issue(
                    "wrong_arguments",
                    "arguments_satisfied",
                    f"Plan step {index} arguments must be an object.",
                    repairable=False,
                )]
            has_value = any(value not in (None, False, "") for value in arguments.values())
            if not has_value:
                return [_issue(
                    "missing_arguments",
                    "arguments_satisfied",
                    f"Plan step {index} has no executable argument.",
                    repairable=False,
                )]
        return []

    @staticmethod
    def _check_evidence_integrity(
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        validator = EvidenceValidator()
        issues = []
        for item in observations:
            validation = validator.validate_observation(item.get("observation", {}))
            issues.extend(
                _issue(
                    issue["type"],
                    "evidence_integrity",
                    issue["message"],
                    repairable=False,
                )
                for issue in validation["issues"]
            )
        return issues

    @staticmethod
    def _check_citations_valid(
        evidence_items: list[dict[str, Any]], citations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        validation = EvidenceValidator().validate(evidence_items, citations)
        return [
            _issue(
                issue["type"],
                "citations_valid",
                issue["message"],
                repairable=False,
            )
            for issue in validation["issues"]
        ]

    @staticmethod
    def _check_citation_coverage(
        evidence_items: list[dict[str, Any]], citations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        evidence_ids = {item["evidence_id"] for item in evidence_items}
        citation_ids = {item.get("evidence_id") for item in citations}
        missing = sorted(evidence_ids - citation_ids)
        if not missing:
            return []
        return [_issue(
            "missing_citation",
            "citation_coverage",
            f"Evidence records are not cited: {missing}",
            repairable=False,
        )]

    @staticmethod
    def _check_version_claims(
        answer: str, evidence_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        claimed_versions = set(re.findall(r"\b\d+\.\d+(?:\.\d+)?\b", answer))
        evidence_text = json.dumps(evidence_items, ensure_ascii=False)
        unsupported = sorted(
            version for version in claimed_versions if version not in evidence_text
        )
        if not unsupported:
            return []
        return [_issue(
            "unsupported_version_claim",
            "version_claims_grounded",
            f"Version claims are not present in Evidence: {unsupported}",
            repairable=True,
        )]

    @staticmethod
    def _check_dependency_direction(
        answer: str, evidence_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        supported = _dependency_pairs(evidence_items)
        claimed = _dependency_claims(answer)
        unsupported = sorted(claimed - supported)
        if not unsupported:
            return []
        rendered = [f"{package}->{dependency}" for package, dependency in unsupported]
        return [_issue(
            "wrong_dependency_direction",
            "dependency_direction_valid",
            f"Dependency claims are not supported in this direction: {rendered}",
            repairable=True,
        )]

    @staticmethod
    def _check_execution_status(
        observations: list[dict[str, Any]], execution_status: str
    ) -> list[dict[str, Any]]:
        expected = aggregate_execution_status(observations)
        if expected == execution_status:
            return []
        return [_issue(
            "execution_status_mismatch",
            "execution_status_consistent",
            f"Execution status should be {expected}, got {execution_status}.",
            repairable=False,
        )]

    @staticmethod
    def _check_not_found_semantics(
        answer: str,
        evidence_items: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        execution_status: str,
    ) -> list[dict[str, Any]]:
        if execution_status != "not_found":
            return []
        issues = []
        if evidence_items or citations:
            issues.append(_issue(
                "not_found_has_evidence",
                "not_found_semantics",
                "A not_found execution must not expose Evidence or Citation.",
                repairable=False,
            ))
        normalized_answer = answer.lower()
        if not any(marker in normalized_answer for marker in ("no ", "not found", "no relevant")):
            issues.append(_issue(
                "not_found_not_expressed",
                "not_found_semantics",
                "The answer does not clearly express that no record was found.",
                repairable=True,
            ))
        return issues

    @staticmethod
    def _check_hybrid_completeness(
        plan: dict[str, Any], observations: list[dict[str, Any]], answer: str
    ) -> list[dict[str, Any]]:
        if plan.get("tool") != "hybrid_plan":
            return []
        missing_messages = [
            item["observation"].get("message")
            for item in observations
            if item["observation"].get("status") != "success"
            and item["observation"].get("message")
        ]
        omitted = [message for message in missing_messages if message not in answer]
        if not omitted:
            return []
        return [_issue(
            "answer_incomplete",
            "hybrid_completeness",
            "Hybrid answer omitted one or more unsuccessful subtask results.",
            repairable=True,
        )]

    @staticmethod
    def _check_answer_nonempty(answer: str) -> list[dict[str, Any]]:
        if answer.strip():
            return []
        return [_issue(
            "answer_empty",
            "answer_nonempty",
            "The Agent answer is empty.",
            repairable=True,
        )]


def aggregate_execution_status(observations: list[dict[str, Any]]) -> str:
    """Aggregate Tool statuses into success/partial/not_found/failed."""
    statuses = [
        item.get("observation", {}).get("status", "failed")
        for item in observations
    ]
    if not statuses or "failed" in statuses:
        return "failed"
    if all(status == "success" for status in statuses):
        return "success"
    if all(status == "not_found" for status in statuses):
        return "not_found"
    if "success" in statuses and all(
        status in {"success", "not_found", "partial_success"} for status in statuses
    ):
        return "partial_success"
    if "partial_success" in statuses:
        return "partial_success"
    return "failed"


def _issue(
    issue_type: str,
    rule: str,
    message: str,
    *,
    repairable: bool,
) -> dict[str, Any]:
    return VerificationIssue(
        type=issue_type,
        severity="error",
        message=message,
        repairable=repairable,
        rule=rule,
    ).to_dict()


def _dependency_pairs(evidence_items: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in evidence_items:
        metadata = item.get("metadata", {})
        if item.get("source_type") == "dependency_record":
            content = json.loads(item["content"])
            pairs.update((content["package"], dependency) for dependency in content["dependencies"])
        elif item.get("source_type") == "dependency_edge":
            pairs.add((metadata["package"], metadata["component"]))
    return pairs


def _dependency_claims(answer: str) -> set[tuple[str, str]]:
    claims: set[tuple[str, str]] = set()
    for match in re.finditer(r"([\w.-]+) depends on:\s*([^;]+)", answer, re.IGNORECASE):
        package = match.group(1)
        payload = re.split(r"\.\s+(?=[A-Z])", match.group(2), maxsplit=1)[0]
        dependencies = [_clean_dependency_token(item) for item in payload.split(",")]
        claims.update((package, dependency) for dependency in dependencies if dependency)
    for match in re.finditer(r"([\w.-]+) is required by:\s*([^;]+)", answer, re.IGNORECASE):
        dependency = match.group(1)
        payload = re.split(r"\.\s+(?=[A-Z])", match.group(2), maxsplit=1)[0]
        packages = [_clean_dependency_token(item) for item in payload.split(",")]
        claims.update((package, dependency) for package in packages if package)
    return claims


def _clean_dependency_token(value: str) -> str:
    token = value.strip()
    return token[:-1] if token.endswith(".") else token
