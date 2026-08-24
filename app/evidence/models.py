"""Models used by the Step 18 evidence layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


VALID_OBSERVATION_STATUSES = {
    "success",
    "partial_success",
    "not_found",
    "failed",
}


@dataclass(frozen=True)
class Evidence:
    """A stable, source-addressable fact produced by an Agent Tool."""

    evidence_id: str
    source_type: str
    source_id: str
    title: str
    content: str
    tool_name: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source_type: str,
        source_id: str,
        title: str,
        content: str,
        tool_name: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> "Evidence":
        identity = json.dumps(
            {
                "source_type": source_type,
                "source_id": source_id,
                "content": content,
                "tool_name": tool_name,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        return cls(
            evidence_id=f"ev_{digest}",
            source_type=source_type,
            source_id=source_id,
            title=title,
            content=content,
            tool_name=tool_name,
            confidence=max(0.0, min(1.0, float(confidence))),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    """A compact answer-facing reference to one Evidence record."""

    evidence_id: str
    title: str
    source_type: str
    snippet: str

    @classmethod
    def from_evidence(cls, evidence: Evidence, snippet_limit: int = 180) -> "Citation":
        compact = " ".join(evidence.content.split())
        snippet = compact[:snippet_limit]
        if len(compact) > snippet_limit:
            snippet = snippet.rstrip() + "..."
        return cls(
            evidence_id=evidence.evidence_id,
            title=evidence.title,
            source_type=evidence.source_type,
            snippet=snippet,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolObservation:
    """The normalized V2 view embedded beside legacy Tool result fields."""

    status: str
    result: Any
    evidence: list[dict[str, Any]]
    error: dict[str, Any] | None
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.status not in VALID_OBSERVATION_STATUSES:
            raise ValueError(f"Unsupported Tool observation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
