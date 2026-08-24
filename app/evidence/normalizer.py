"""Convert legacy Tool outputs into stable Evidence and ToolObservation objects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.evidence.models import Citation, Evidence, ToolObservation


class EvidenceNormalizer:
    """Normalize all five current Tool output shapes without removing legacy fields."""

    def normalize(
        self,
        tool_name: str,
        observation: dict[str, Any],
        *,
        latency_ms: float,
    ) -> dict[str, Any]:
        evidence = self._build_evidence(tool_name, observation)
        evidence_dicts = [item.to_dict() for item in evidence]
        status = observation.get("status", "failed")
        error = self._error_payload(status, observation)
        metadata = dict(observation.get("metadata", {}))
        metadata.update({
            "latency_ms": round(max(0.0, latency_ms), 3),
            "evidence_normalized": True,
            "evidence_count": len(evidence_dicts),
            "observation_schema_version": "tool-observation-v2",
        })
        normalized = ToolObservation(
            status=status,
            result=self._result_payload(tool_name, observation),
            evidence=evidence_dicts,
            error=error,
            metadata=metadata,
        )

        enriched = dict(observation)
        enriched["evidence_items"] = evidence_dicts
        enriched["error"] = error
        enriched["metadata"] = metadata
        enriched["normalized_observation"] = normalized.to_dict()
        return enriched

    def _build_evidence(
        self,
        tool_name: str,
        observation: dict[str, Any],
    ) -> list[Evidence]:
        if observation.get("status") != "success":
            return []
        builders = {
            "package_search": self._package_evidence,
            "dependency_analysis": self._dependency_evidence,
            "version_compare": self._version_evidence,
            "component_mapping": self._component_evidence,
            "rag_retrieval": self._rag_evidence,
        }
        builder = builders.get(tool_name)
        return builder(observation) if builder else []

    @staticmethod
    def _package_evidence(observation: dict[str, Any]) -> list[Evidence]:
        result = observation.get("result")
        records = result if isinstance(result, list) else [result] if result else []
        return [
            Evidence.create(
                source_type="package_record",
                source_id=(
                    f"packages.json#package={record['package']};"
                    f"release={record['release']};architecture={record['architecture']}"
                ),
                title=f"Package {record['package']} {record['version']}",
                content=_canonical_content(record),
                tool_name="package_search",
                metadata={
                    "package": record["package"],
                    "release": record["release"],
                    "architecture": record["architecture"],
                },
            )
            for record in records
        ]

    @staticmethod
    def _dependency_evidence(observation: dict[str, Any]) -> list[Evidence]:
        if observation.get("result_type") == "reverse_dependency":
            component = observation["component"]
            return [
                Evidence.create(
                    source_type="dependency_edge",
                    source_id=f"dependencies.json#package={package};requires={component}",
                    title=f"Dependency edge: {package} requires {component}",
                    content=_canonical_content({
                        "package": package,
                        "requires": component,
                        "direction": "required_by",
                    }),
                    tool_name="dependency_analysis",
                    metadata={
                        "package": package,
                        "component": component,
                        "direction": "required_by",
                    },
                )
                for package in observation.get("dependents", [])
            ]

        package = observation.get("package")
        if not package:
            return []
        dependencies = observation.get("dependencies", [])
        return [
            Evidence.create(
                source_type="dependency_record",
                source_id=f"dependencies.json#package={package}",
                title=f"Dependencies of {package}",
                content=_canonical_content({
                    "package": package,
                    "dependencies": dependencies,
                }),
                tool_name="dependency_analysis",
                metadata={
                    "package": package,
                    "dependency_count": len(dependencies),
                    "direction": "depends_on",
                },
            )
        ]

    @staticmethod
    def _version_evidence(observation: dict[str, Any]) -> list[Evidence]:
        package = observation.get("package")
        if not package:
            return []
        record = {
            "package": package,
            "old_version": observation.get("old_version"),
            "new_version": observation.get("new_version"),
            "changes": observation.get("changes", []),
        }
        return [
            Evidence.create(
                source_type="version_record",
                source_id=(
                    f"versions.json#package={package};"
                    f"from={record['old_version']};to={record['new_version']}"
                ),
                title=f"Version change for {package}",
                content=_canonical_content(record),
                tool_name="version_compare",
                metadata={
                    "package": package,
                    "old_version": record["old_version"],
                    "new_version": record["new_version"],
                },
            )
        ]

    @staticmethod
    def _component_evidence(observation: dict[str, Any]) -> list[Evidence]:
        component = observation.get("component")
        return [
            Evidence.create(
                source_type="component_mapping",
                source_id=(
                    f"packages.json#component={component};"
                    f"package={owner['package']};release={owner['release']}"
                ),
                title=f"Component ownership: {component}",
                content=_canonical_content({
                    "component": component,
                    "owner_package": owner,
                }),
                tool_name="component_mapping",
                metadata={
                    "component": component,
                    "package": owner["package"],
                    "release": owner["release"],
                },
            )
            for owner in observation.get("owners", [])
        ]

    @staticmethod
    def _rag_evidence(observation: dict[str, Any]) -> list[Evidence]:
        evidence = []
        for rank, result in enumerate(observation.get("results", []), start=1):
            source = Path(result["source"]).name
            content = result["content"]
            content_key = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            source_id = result.get("chunk_id") or f"{source}#{result['title']}#chunk={content_key}"
            evidence.append(Evidence.create(
                source_type="document_chunk",
                source_id=source_id,
                title=result["title"],
                content=content,
                tool_name="rag_retrieval",
                confidence=_retrieval_confidence(result.get("score", 0.0)),
                metadata={
                    "source": source,
                    "rank": rank,
                    "score": result.get("score", 0.0),
                    "matched_terms": result.get("matched_terms", []),
                    "chunk_id": result.get("chunk_id"),
                    "document_id": result.get("document_id"),
                    "retriever_mode": result.get("retriever_mode"),
                    "scores": result.get("scores", {}),
                },
            ))
        return evidence

    @staticmethod
    def _result_payload(tool_name: str, observation: dict[str, Any]) -> Any:
        if tool_name == "package_search":
            return observation.get("result")
        if tool_name == "dependency_analysis":
            if observation.get("result_type") == "reverse_dependency":
                return {
                    "component": observation.get("component"),
                    "dependents": observation.get("dependents", []),
                }
            return {
                "package": observation.get("package"),
                "dependencies": observation.get("dependencies", []),
            } if observation.get("package") else None
        if tool_name == "version_compare":
            return {
                "package": observation.get("package"),
                "old_version": observation.get("old_version"),
                "new_version": observation.get("new_version"),
                "changes": observation.get("changes", []),
            } if observation.get("package") else None
        if tool_name == "component_mapping":
            return {
                "component": observation.get("component"),
                "owners": observation.get("owners", []),
            } if observation.get("component") else None
        if tool_name == "rag_retrieval":
            return observation.get("results", [])
        return None

    @staticmethod
    def _error_payload(status: str, observation: dict[str, Any]) -> dict[str, Any] | None:
        if status != "failed":
            return None
        return {
            "type": observation.get("error_type", "tool_execution_failed"),
            "message": observation.get("message", "Tool execution failed."),
        }


def citations_from_evidence(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create one compact Citation per unique Evidence record."""
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence_items:
        evidence_id = item["evidence_id"]
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        evidence = Evidence(**item)
        citations.append(Citation.from_evidence(evidence).to_dict())
    return citations


def _canonical_content(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _retrieval_confidence(score: float) -> float:
    score = max(0.0, float(score))
    return score / (score + 1.0) if score else 0.5
