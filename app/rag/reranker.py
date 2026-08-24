"""Deterministic domain-aware reranking for Hybrid RAG."""

from __future__ import annotations

import re
from pathlib import Path

from app.rag.chunker import DocumentChunk
from app.rag.embedding import tokenize, tokenize_terms


PACKAGE_NAMES = ("openssl", "ethtool", "nginx", "tcpdump")


class DeterministicReranker:
    def score(self, query: str, chunk: DocumentChunk) -> tuple[float, dict[str, float]]:
        lowered = query.lower()
        expanded_terms = set(tokenize_terms(query, expand_query=True))
        chunk_terms = tokenize(f"{chunk.title} {chunk.section} {chunk.content}")
        package_score = sum(
            4.0 for package in PACKAGE_NAMES
            if package in expanded_terms and package in chunk_terms
        )
        release_match = re.search(r"\b\d{4}\b", query)
        release_score = 6.0 if release_match and chunk.version == release_match.group(0) else 0.0
        title_score = 0.75 * len(expanded_terms & tokenize(chunk.title))

        source_score = 0.0
        source_stem = Path(chunk.source).stem
        if ("manual" in lowered or "手册" in query) and source_stem == "software_manual":
            source_score = 3.0
        if any(term in lowered for term in ("release", "note")) or "发布" in query:
            if source_stem == "release_note":
                source_score = 3.0

        section_score = 1.0 if expanded_terms & tokenize(chunk.section) else 0.0
        features = {
            "package_exact": package_score,
            "release_exact": release_score,
            "title_match": title_score,
            "source_intent": source_score,
            "section_match": section_score,
        }
        return sum(features.values()), features
