"""Small deterministic BM25 index for offline engineering-document retrieval."""

from __future__ import annotations

import math
from collections import Counter

from app.rag.chunker import DocumentChunk
from app.rag.embedding import tokenize_terms


class BM25Index:
    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        title_weight: int = 3,
    ) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.documents = [
            tokenize_terms(chunk.title) * title_weight
            + tokenize_terms(chunk.section) * title_weight
            + tokenize_terms(chunk.content)
            for chunk in chunks
        ]
        self.term_frequencies = [Counter(document) for document in self.documents]
        self.document_lengths = [len(document) for document in self.documents]
        self.average_length = (
            sum(self.document_lengths) / len(self.document_lengths)
            if self.document_lengths else 0.0
        )
        self.document_frequency = Counter(
            token for document in self.documents for token in set(document)
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        source_filter: str | None = None,
        version_filter: str | None = None,
    ) -> list[dict]:
        query_terms = tokenize_terms(query, expand_query=True)
        if not query_terms:
            return []
        scored = []
        for index, chunk in enumerate(self.chunks):
            if source_filter and chunk.document_id != source_filter:
                continue
            if version_filter and chunk.version != version_filter:
                continue
            score, matched = self._score(index, query_terms)
            if score > 0:
                scored.append({
                    "chunk": chunk,
                    "bm25_score": round(score, 8),
                    "matched_terms": sorted(matched),
                })
        scored.sort(key=lambda item: (-item["bm25_score"], item["chunk"].chunk_id))
        return scored[:top_k]

    def _score(self, index: int, query_terms: list[str]) -> tuple[float, set[str]]:
        frequencies = self.term_frequencies[index]
        document_length = self.document_lengths[index]
        total_documents = len(self.documents)
        score = 0.0
        matched: set[str] = set()
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            matched.add(term)
            document_frequency = self.document_frequency[term]
            inverse_document_frequency = math.log(
                1 + (total_documents - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            length_normalizer = 1 - self.b
            if self.average_length:
                length_normalizer += self.b * document_length / self.average_length
            score += inverse_document_frequency * (
                frequency * (self.k1 + 1)
                / (frequency + self.k1 * length_normalizer)
            )
        return score, matched
