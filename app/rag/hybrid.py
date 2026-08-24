"""RRF fusion of legacy overlap and BM25 with deterministic reranking."""

from __future__ import annotations

from pathlib import Path

from app.rag.bm25 import BM25Index
from app.rag.chunker import DocumentChunk
from app.rag.embedding import tokenize
from app.rag.reranker import DeterministicReranker
from app.rag.vector_store import SimpleVectorStore


class HybridRetriever:
    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        rrf_k: int = 60,
        rrf_weight: float = 100.0,
        reranker_weight: float = 1.0,
    ) -> None:
        self.chunks = chunks
        self.legacy_store = SimpleVectorStore(chunks)
        self.bm25 = BM25Index(chunks)
        self.reranker = DeterministicReranker()
        self.rrf_k = rrf_k
        self.rrf_weight = rrf_weight
        self.reranker_weight = reranker_weight

    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        source_filter: str | None = None,
        version_filter: str | None = None,
    ) -> list[dict]:
        legacy = self._legacy_search(
            query,
            top_k=20,
            source_filter=source_filter,
            version_filter=version_filter,
        )
        bm25 = self.bm25.search(
            query,
            top_k=20,
            source_filter=source_filter,
            version_filter=version_filter,
        )
        candidates: dict[str, dict] = {}
        for rank, item in enumerate(legacy, start=1):
            candidate = candidates.setdefault(item["chunk"].chunk_id, _candidate(item["chunk"]))
            candidate["legacy_score"] = item["score"]
            candidate["legacy_matched_terms"] = item["matched_terms"]
            candidate["rrf_score"] += 1.0 / (self.rrf_k + rank)
        for rank, item in enumerate(bm25, start=1):
            candidate = candidates.setdefault(item["chunk"].chunk_id, _candidate(item["chunk"]))
            candidate["bm25_score"] = item["bm25_score"]
            candidate["bm25_matched_terms"] = item["matched_terms"]
            candidate["rrf_score"] += 1.0 / (self.rrf_k + rank)

        ranked = []
        for candidate in candidates.values():
            rerank_score, features = self.reranker.score(query, candidate["chunk"])
            candidate["rerank_score"] = rerank_score
            candidate["rerank_features"] = features
            candidate["final_score"] = (
                self.rrf_weight * candidate["rrf_score"]
                + self.reranker_weight * rerank_score
            )
            ranked.append(candidate)
        ranked.sort(key=lambda item: (-item["final_score"], item["chunk"].chunk_id))
        return ranked[:top_k]

    def _legacy_search(
        self,
        query: str,
        *,
        top_k: int,
        source_filter: str | None,
        version_filter: str | None,
    ) -> list[dict]:
        results = self.legacy_store.search(query, top_k=len(self.chunks))
        preferred_sources = set()
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
            if Path(chunk.source).stem in preferred_sources:
                adjusted["score"] += 5
            filtered.append(adjusted)
        filtered.sort(key=lambda item: (-item["score"], item["chunk"].chunk_id))
        return filtered[:top_k]


def _candidate(chunk: DocumentChunk) -> dict:
    return {
        "chunk": chunk,
        "legacy_score": 0.0,
        "bm25_score": 0.0,
        "rrf_score": 0.0,
        "rerank_score": 0.0,
        "rerank_features": {},
        "legacy_matched_terms": [],
        "bm25_matched_terms": [],
        "final_score": 0.0,
    }
