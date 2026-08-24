"""Simple in-memory vector store for document chunks."""

from __future__ import annotations

from app.rag.chunker import DocumentChunk
from app.rag.embedding import tokenize


class SimpleVectorStore:
    """Rank chunks with token-overlap similarity."""

    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = chunks
        self.index = [
            {
                "chunk": chunk,
                "title_tokens": tokenize(chunk.title),
                "content_tokens": tokenize(chunk.content),
                "source_tokens": tokenize(chunk.source)
            }
            for chunk in chunks
        ]

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        query_tokens = tokenize(query)
        scored = []
        for item in self.index:
            title_overlap = query_tokens & item["title_tokens"]
            content_overlap = query_tokens & item["content_tokens"]
            source_overlap = query_tokens & item["source_tokens"]
            overlap = title_overlap | content_overlap | source_overlap
            score = len(content_overlap) + (3 * len(title_overlap)) + (2 * len(source_overlap))
            if score:
                scored.append({
                    "score": score,
                    "matched_terms": sorted(overlap),
                    "chunk": item["chunk"]
                })

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]
