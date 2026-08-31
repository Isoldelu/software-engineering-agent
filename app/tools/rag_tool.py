"""RAG retriever tool for simulated engineering documents."""

from __future__ import annotations

import re
from pathlib import Path

from app.rag.retriever import DEFAULT_DOCS_DIR, DocumentRetriever
from app.tools.base import execute_tool_call


class RAGRetrieverTool:
    name = "rag_retrieval"
    description = "Retrieve relevant release note or software manual chunks."

    def __init__(
        self,
        docs_dir: str | Path = DEFAULT_DOCS_DIR,
        *,
        mode: str | None = None,
        hybrid_weights: dict[str, float] | None = None,
    ) -> None:
        self.docs_dir = Path(docs_dir)
        self.retriever = DocumentRetriever(
            self.docs_dir,
            mode=mode,
            hybrid_weights=hybrid_weights,
        )

    def run(self, query: str) -> dict:
        """Retrieve documents and return a normalized Tool observation."""
        return execute_tool_call(self.name, query, self._run)

    def _run(self, query: str) -> dict:
        """Retrieve relevant document evidence for a query."""
        release = self._extract_release(query)
        results = self.retriever.retrieve(
            query,
            top_k=3,
            version_filter=release,
        )
        return {
            "tool": self.name,
            "status": "success" if results else "not_found",
            "query": query,
            "results": results,
            "retriever_mode": self.retriever.mode,
            "evidence": sorted({item["source"] for item in results}),
            "message": None if results else self._not_found_message(release)
        }

    @staticmethod
    def _extract_release(query: str) -> str | None:
        match = re.search(r"\b\d{4}\b", query)
        return match.group(0) if match else None

    @staticmethod
    def _not_found_message(release: str | None) -> str:
        if release:
            return f"No relevant document chunk matched release {release} in the simulated documents."
        return "No relevant document chunk matched the simulated documents."
