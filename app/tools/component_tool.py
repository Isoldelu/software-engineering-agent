"""Component mapping tool.

This tool maps files/components such as libssl.so back to the simulated package
that owns them. It supports the common AI4SE question: which package contains
this binary, shared library, or component?
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.tools.base import execute_tool_call


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "packages.json"


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize(text: str) -> str:
    return text.lower().strip()


class ComponentMappingTool:
    name = "component_mapping"
    description = "Map a binary, shared library, or component file to its package."

    def __init__(self, data_path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.data_path = Path(data_path)
        self.packages = _load_json(self.data_path)

    def run(self, query: str) -> dict:
        """Map a component and return a normalized Tool observation."""
        return execute_tool_call(self.name, query, self._run)

    def _run(self, query: str) -> dict:
        """Find the simulated package that owns a file or component."""
        component = self._extract_component(query)
        if not component:
            return {
                "tool": self.name,
                "status": "not_found",
                "query": query,
                "message": "No component name matched the simulated package file list.",
                "known_components": self._known_components(),
                "evidence": str(self.data_path)
            }

        owners = [
            package for package in self.packages
            if any(_normalize(file_name) == _normalize(component) for file_name in package.get("files", []))
        ]

        return {
            "tool": self.name,
            "status": "success" if owners else "not_found",
            "query": query,
            "component": component,
            "owners": owners,
            "evidence": str(self.data_path),
            "message": None if owners else f"No package owns component {component} in the simulated dataset."
        }

    def _extract_component(self, query: str) -> str | None:
        normalized_query = _normalize(query)
        for component in self._known_components():
            if _normalize(component) in normalized_query:
                return component

        match = re.search(r"[\w.-]+\.(?:so|ko|bin|conf|service|rpm)", normalized_query)
        return match.group(0) if match else None

    def _known_components(self) -> list[str]:
        components: list[str] = []
        for package in self.packages:
            components.extend(package.get("files", []))
        return sorted(set(components))
