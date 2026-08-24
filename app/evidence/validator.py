"""Deterministic validation for Evidence and Citation integrity."""

from __future__ import annotations

from typing import Any

from app.evidence.models import VALID_OBSERVATION_STATUSES


class EvidenceValidator:
    """Validate IDs, normalized observations, and Citation references."""

    def validate(
        self,
        evidence_items: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        evidence_ids = [item.get("evidence_id") for item in evidence_items]
        valid_ids = {item for item in evidence_ids if item}

        if len(valid_ids) != len(evidence_ids):
            issues.append({
                "type": "duplicate_or_missing_evidence_id",
                "message": "Evidence IDs must be present and unique.",
            })

        for item in evidence_items:
            missing = [
                field for field in (
                    "evidence_id",
                    "source_type",
                    "source_id",
                    "title",
                    "content",
                    "tool_name",
                    "confidence",
                    "metadata",
                )
                if field not in item
            ]
            if missing:
                issues.append({
                    "type": "invalid_evidence_schema",
                    "message": f"Evidence is missing fields: {', '.join(missing)}",
                })

        for citation in citations:
            if citation.get("evidence_id") not in valid_ids:
                issues.append({
                    "type": "invalid_citation_reference",
                    "message": (
                        f"Citation {citation.get('evidence_id')} does not reference "
                        "current Evidence."
                    ),
                })

        return {
            "valid": not issues,
            "evidence_count": len(evidence_items),
            "citation_count": len(citations),
            "issues": issues,
        }

    def validate_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        normalized = observation.get("normalized_observation")
        issues: list[dict[str, str]] = []
        if not isinstance(normalized, dict):
            issues.append({
                "type": "missing_normalized_observation",
                "message": "Tool output does not contain normalized_observation.",
            })
        else:
            missing = [
                field for field in ("status", "result", "evidence", "error", "metadata")
                if field not in normalized
            ]
            if missing:
                issues.append({
                    "type": "invalid_observation_schema",
                    "message": f"Normalized observation is missing: {', '.join(missing)}",
                })
            if normalized.get("status") not in VALID_OBSERVATION_STATUSES:
                issues.append({
                    "type": "invalid_observation_status",
                    "message": f"Unsupported status: {normalized.get('status')}",
                })
            if normalized.get("status") == "success" and not normalized.get("evidence"):
                issues.append({
                    "type": "missing_success_evidence",
                    "message": "Successful Tool observations must contain Evidence.",
                })
            if normalized.get("status") == "not_found" and normalized.get("evidence"):
                issues.append({
                    "type": "not_found_has_evidence",
                    "message": "not_found observations must not fabricate Evidence.",
                })

        return {
            "valid": not issues,
            "issues": issues,
        }
