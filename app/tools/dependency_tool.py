"""Dependency analysis tool.

This deterministic tool reads simulated dependency relationships from
data/dependencies.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.tools.base import execute_tool_call


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "dependencies.json"


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize(text: str) -> str:
    return text.lower().strip()


class DependencyAnalysisTool:
    name = "dependency_analysis"
    description = "Analyze package dependencies and related shared libraries."

    def __init__(self, data_path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.data_path = Path(data_path)
        self.dependencies = _load_json(self.data_path)

    def run(self, query: str) -> dict:
        """Analyze dependencies and return a normalized Tool observation."""
        return execute_tool_call(self.name, query, self._run)

    def _run(self, query: str) -> dict:
        """Return direct dependencies for a package mentioned in the query."""
        normalized_query = _normalize(query)
        reverse_dependency = self._find_reverse_dependency(normalized_query)
        if reverse_dependency:
            component, dependents = reverse_dependency
            return {
                "tool": self.name,
                "status": "success",
                "query": query,
                "result_type": "reverse_dependency",
                "component": component,
                "dependents": dependents,
                "summary": self._format_reverse_dependency(component, dependents),
                "evidence": str(self.data_path)
            }

        matched_dependency = self._find_dependency(normalized_query)

        if matched_dependency:
            return {
                "tool": self.name,
                "status": "success",
                "query": query,
                "package": matched_dependency["package"],
                "dependencies": matched_dependency.get("dependencies", []),
                "dependency_tree": self._format_dependency_tree(matched_dependency),
                "evidence": str(self.data_path)
            }

        return {
            "tool": self.name,
            "status": "not_found",
            "query": query,
            "message": "No package dependency record matched the simulated dependency dataset.",
            "available_packages": [item["package"] for item in self.dependencies],
            "evidence": str(self.data_path)
        }

    def _find_dependency(self, normalized_query: str) -> dict | None:
        for item in self.dependencies:
            if _normalize(item["package"]) in normalized_query:
                return item
        return None

    def _find_reverse_dependency(self, normalized_query: str) -> tuple[str, list[str]] | None:
        component = self._extract_component(normalized_query)
        if not component:
            return None

        dependents = [
            item["package"] for item in self.dependencies
            if any(_normalize(dependency) == _normalize(component) for dependency in item.get("dependencies", []))
        ]
        return (component, dependents) if dependents else None

    @staticmethod
    def _extract_component(normalized_query: str) -> str | None:
        match = re.search(r"[\w.-]+\.(?:so|ko|bin|conf|service|rpm)", normalized_query)
        return match.group(0) if match else None

    @staticmethod
    def _format_dependency_tree(dependency: dict) -> str:
        lines = [dependency["package"]]
        lines.extend(f"|-- {name}" for name in dependency.get("dependencies", []))
        return "\n".join(lines)

    @staticmethod
    def _format_reverse_dependency(component: str, dependents: list[str]) -> str:
        names = ", ".join(dependents)
        return f"{component} is required by: {names}."
