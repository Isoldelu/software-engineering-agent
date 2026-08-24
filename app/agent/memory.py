"""Persistent trajectory memory for Agent runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAJECTORY_PATH = PROJECT_ROOT / "data" / "trajectories.jsonl"


class TrajectoryMemory:
    """Append-only JSONL storage for Agent execution traces."""

    def __init__(self, path: str | Path = DEFAULT_TRAJECTORY_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, agent_result: dict) -> dict:
        """Persist one Agent result and return metadata about the write."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": agent_result.get("trace_id"),
            "session_id": agent_result.get("session_id"),
            "parent_trace_id": agent_result.get("parent_trace_id"),
            "policy_version": agent_result.get("policy_version"),
            "policy_assignment": agent_result.get("policy_assignment", {}),
            "query": agent_result["query"],
            "resolved_query": agent_result.get("resolved_query", agent_result["query"]),
            "intent": agent_result["intent"],
            "selected_tool": agent_result["selected_tool"],
            "arguments": agent_result.get("arguments", {}),
            "answer": agent_result["answer"],
            "used_tools": agent_result.get("used_tools", []),
            "evidence": agent_result.get("evidence", []),
            "evidence_items": agent_result.get("evidence_items", []),
            "citations": agent_result.get("citations", []),
            "evidence_count": agent_result.get("evidence_count", 0),
            "execution_status": agent_result.get("execution_status"),
            "verification": agent_result.get("verification", {}),
            "confidence": agent_result.get("confidence", "medium"),
            "success": agent_result.get("success", False),
            "trajectory": agent_result.get("trajectory", []),
            "trace": agent_result.get("trace", {}),
        }
        try:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            return {
                "path": str(self.path),
                "recorded": True
            }
        except OSError as exc:
            return {
                "path": str(self.path),
                "recorded": False,
                "error": str(exc)
            }
