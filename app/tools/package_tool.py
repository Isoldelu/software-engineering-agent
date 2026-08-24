"""Package search tool.

This deterministic tool reads simulated package metadata from data/packages.json.
It is intentionally simple so it can later be wrapped by LangGraph or function
calling without changing its public run(query) interface.
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


class PackageSearchTool:
    name = "package_search"
    description = "Search package metadata such as version, release, architecture, and files."

    def __init__(self, data_path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.data_path = Path(data_path)
        self.packages = _load_json(self.data_path)

    def run(self, query: str) -> dict:
        """Search packages and return a normalized Tool observation."""
        return execute_tool_call(self.name, query, self._run)

    def _run(self, query: str) -> dict:
        """Search packages by package name or release id."""
        normalized_query = _normalize(query)
        matched_package = self._find_package(normalized_query)
        if matched_package:
            return {
                "tool": self.name,
                "status": "success",
                "query": query,
                "result_type": "package",
                "result": matched_package,
                "evidence": str(self.data_path)
            }

        release = self._extract_release(normalized_query)
        if release:
            packages = [
                package for package in self.packages
                if package.get("release") == release
            ]
            return {
                "tool": self.name,
                "status": "success" if packages else "not_found",
                "query": query,
                "result_type": "release_packages",
                "release": release,
                "result": packages,
                "message": None if packages else f"No package records were found for release {release}.",
                "evidence": str(self.data_path)
            }

        return {
            "tool": self.name,
            "status": "not_found",
            "query": query,
            "message": "No package name or release id matched the simulated package dataset.",
            "available_packages": [package["package"] for package in self.packages],
            "evidence": str(self.data_path)
        }

    def _find_package(self, normalized_query: str) -> dict | None:
        for package in self.packages:
            if _normalize(package["package"]) in normalized_query:
                return package
        return None

    @staticmethod
    def _extract_release(normalized_query: str) -> str | None:
        match = re.search(r"\b\d{4}\b", normalized_query)
        return match.group(0) if match else None
