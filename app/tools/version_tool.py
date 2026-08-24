"""Version comparison tool.

This deterministic tool reads simulated version changes from data/versions.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.tools.base import execute_tool_call


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "versions.json"


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize(text: str) -> str:
    return text.lower().strip()


class VersionCompareTool:
    name = "version_compare"
    description = "Compare package versions and summarize version changes."

    def __init__(self, data_path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.data_path = Path(data_path)
        self.versions = _load_json(self.data_path)

    def run(self, query: str) -> dict:
        """Compare versions and return a normalized Tool observation."""
        return execute_tool_call(self.name, query, self._run)

    def _run(self, query: str) -> dict:
        """Return version changes for a package mentioned in the query."""
        normalized_query = _normalize(query)
        matched_version = self._find_version_record(normalized_query)

        if matched_version:
            return {
                "tool": self.name,
                "status": "success",
                "query": query,
                "package": matched_version["package"],
                "old_version": matched_version["old_version"],
                "new_version": matched_version["new_version"],
                "changes": matched_version.get("changes", []),
                "summary": self._format_summary(matched_version),
                "evidence": str(self.data_path)
            }

        return {
            "tool": self.name,
            "status": "not_found",
            "query": query,
            "message": "No version change record matched the simulated version dataset.",
            "available_packages": [item["package"] for item in self.versions],
            "evidence": str(self.data_path)
        }

    def _find_version_record(self, normalized_query: str) -> dict | None:
        for item in self.versions:
            if _normalize(item["package"]) in normalized_query:
                return item
        return None

    @staticmethod
    def _format_summary(version_record: dict) -> str:
        changes = "\n".join(f"- {change}" for change in version_record.get("changes", []))
        return (
            f"{version_record['package']} changed from "
            f"{version_record['old_version']} to {version_record['new_version']}:\n"
            f"{changes}"
        )
