"""Configurable legacy, BM25, and Hybrid document retrieval."""

from __future__ import annotations

import os
from pathlib import Path

from app.rag.bm25 import BM25Index
from app.rag.chunker import DocumentChunk, load_markdown_chunks
from app.rag.embedding import tokenize
from app.rag.hybrid import HybridRetriever
from app.rag.vector_store import SimpleVectorStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCS_DIR = PROJECT_ROOT / "data" / "documents"
VALID_RETRIEVAL_MODES = {"legacy", "bm25", "hybrid"}
# V1 remains the runtime default for contract compatibility. Deployments can set
# SOFTWARE_AGENT_RAG_MODE=hybrid after reviewing the Step 20 ablation report.
DEFAULT_RETRIEVAL_MODE = "legacy"


class DocumentRetriever:
    """Retrieve standard document chunks with a selectable offline strategy."""

    def __init__(
        self,
        docs_dir: str | Path = DEFAULT_DOCS_DIR,
        *,
        mode: str | None = None,
        hybrid_weights: dict[str, float] | None = None,
    ) -> None:
        self.docs_dir = Path(docs_dir)
        configured_mode = (
            mode
            or os.getenv("SOFTWARE_AGENT_RAG_MODE")
            or DEFAULT_RETRIEVAL_MODE
        )
        self.mode = _validate_mode(configured_mode)
        self.chunks = load_markdown_chunks(self.docs_dir)
        self.vector_store = SimpleVectorStore(self.chunks)
        self.bm25_index = BM25Index(self.chunks)
        weights = hybrid_weights or {}
        self.hybrid_retriever = HybridRetriever(
            self.chunks,
            rrf_weight=float(weights.get("rrf_weight", 100.0)),
            reranker_weight=float(weights.get("reranker_weight", 1.0)),
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        *,
        mode: str | None = None,
        source_filter: str | None = None,
        version_filter: str | None = None,
    ) -> list[dict]:
        """Return deterministic ranked chunks with per-stage score details."""
        selected_mode = _validate_mode(mode or self.mode)
        if not query.strip() or top_k <= 0:
            return []
        if selected_mode == "legacy":
            ranked = self._legacy_search(
                query,
                top_k=top_k,
                source_filter=source_filter,
                version_filter=version_filter,
            )
        elif selected_mode == "bm25":
            ranked = self.bm25_index.search(
                query,
                top_k=top_k,
                source_filter=source_filter,
                version_filter=version_filter,
            )
        else:
            ranked = self.hybrid_retriever.search(
                query,
                top_k=top_k,
                source_filter=source_filter,
                version_filter=version_filter,
            )
        return [
            self._serialize_result(item, selected_mode, rank)
            for rank, item in enumerate(ranked, start=1)
        ]

    def _legacy_search(
        self,
        query: str,
        *,
        top_k: int,
        source_filter: str | None,
        version_filter: str | None,
    ) -> list[dict]:
        search_limit = len(self.chunks) if source_filter or version_filter else top_k
        results = self.vector_store.search(query, top_k=search_limit)
        preferred_sources: set[str] = set()
        query_tokens = tokenize(query)
        if "manual" in query_tokens:
            preferred_sources.add("software_manual")
        if "release" in query_tokens or "note" in query_tokens:
            preferred_sources.add("release_note")

        filtered = []
        for item in results:
            chunk = item["chunk"]
            if source_filter and chunk.document_id != source_filter:
                continue
            if version_filter and chunk.version != version_filter:
                continue
            adjusted = dict(item)
            if chunk.document_id in preferred_sources:
                adjusted["score"] += 5
            filtered.append(adjusted)
        # Stable score-only sorting reproduces the V1 insertion-order tie behavior.
        filtered.sort(key=lambda item: item["score"], reverse=True)
        return filtered[:top_k]

    @staticmethod
    def _serialize_result(item: dict, mode: str, rank: int) -> dict:
        chunk: DocumentChunk = item["chunk"]
        legacy_score = float(item.get("legacy_score", item.get("score", 0.0)))
        bm25_score = float(item.get("bm25_score", 0.0))
        matched_terms = item.get("legacy_matched_terms") or item.get("matched_terms", [])
        if not matched_terms:
            matched_terms = item.get("bm25_matched_terms", [])
        compatibility_score = legacy_score or bm25_score
        return {
            "source": chunk.source,
            "title": chunk.title,
            "content": chunk.content,
            "score": compatibility_score,
            "matched_terms": matched_terms,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "section": chunk.section,
            "version": chunk.version,
            "metadata": dict(chunk.metadata),
            "retriever_mode": mode,
            "rank": rank,
            "scores": {
                "legacy": legacy_score,
                "bm25": bm25_score,
                "rrf": round(float(item.get("rrf_score", 0.0)), 8),
                "reranker": float(item.get("rerank_score", 0.0)),
                "final": round(float(item.get("final_score", compatibility_score)), 8),
                "reranker_features": item.get("rerank_features", {}),
            },
        }


def _validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in VALID_RETRIEVAL_MODES:
        expected = ", ".join(sorted(VALID_RETRIEVAL_MODES))
        raise ValueError(f"Unsupported retrieval mode '{mode}'. Expected one of: {expected}.")
    return normalized
