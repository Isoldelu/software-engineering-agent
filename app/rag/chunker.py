"""Deterministic Markdown chunking with stable engineering-document metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    source: str
    title: str
    section: str
    content: str
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkdownChunker:
    """Split Markdown at headings while keeping stable IDs and section metadata."""

    def chunk_file(self, path: Path) -> list[DocumentChunk]:
        document_id = path.stem
        document_title = document_id
        current_section = document_id
        current_lines: list[str] = []
        chunks: list[DocumentChunk] = []

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                if current_lines:
                    chunks.append(self._build_chunk(
                        path,
                        document_id,
                        document_title,
                        current_section,
                        current_lines,
                    ))
                    current_lines = []
                heading_level = len(line) - len(line.lstrip("#"))
                heading = line.lstrip("#").strip() or document_id
                if heading_level == 1:
                    document_title = heading
                current_section = heading
            else:
                current_lines.append(line)

        if current_lines:
            chunks.append(self._build_chunk(
                path,
                document_id,
                document_title,
                current_section,
                current_lines,
            ))
        return [chunk for chunk in chunks if chunk.content]

    @staticmethod
    def _build_chunk(
        path: Path,
        document_id: str,
        document_title: str,
        section: str,
        lines: list[str],
    ) -> DocumentChunk:
        content = "\n".join(lines).strip()
        version_match = re.search(r"\b\d{4}\b", section)
        return DocumentChunk(
            chunk_id=f"{document_id}:{_slug(section)}",
            document_id=document_id,
            source=str(path),
            title=section,
            section=section,
            content=content,
            version=version_match.group(0) if version_match else None,
            metadata={
                "document_title": document_title,
                "format": "markdown",
            },
        )


def load_markdown_chunks(docs_dir: Path) -> list[DocumentChunk]:
    chunker = MarkdownChunker()
    return [
        chunk
        for path in sorted(docs_dir.glob("*.md"))
        for chunk in chunker.chunk_file(path)
    ]


def _slug(value: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", value.lower())
    return "-".join(tokens) or "section"
