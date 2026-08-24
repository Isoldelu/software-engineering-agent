"""Lightweight text embedding helpers.

This module intentionally avoids external dependencies. It creates sparse token
sets for a first-pass RAG demo. A later FAISS-backed implementation can replace
this without changing the retriever interface.
"""

from __future__ import annotations

import re


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+")
STOPWORDS = {
    "a",
    "an",
    "as",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "was",
    "what",
}

QUERY_EXPANSIONS = {
    "抓包": ("tcpdump", "packet", "capture"),
    "抓包工具": ("tcpdump", "packet", "capture"),
    "安全通信": ("openssl", "secure", "communication", "tls"),
    "安全通信库": ("openssl", "secure", "communication", "tls"),
    "加密": ("openssl", "encryption", "tls"),
    "网口": ("ethtool", "network", "interface", "link"),
    "网卡": ("ethtool", "network", "interface", "link"),
    "诊断工具": ("ethtool", "diagnostics", "interface"),
    "管理面": ("nginx", "management-plane", "web", "http"),
    "发布说明": ("release", "note"),
    "发布": ("release",),
    "手册": ("manual",),
    "组件": ("component", "components"),
    "依赖": ("depends", "requires"),
}


def tokenize(text: str) -> set[str]:
    """Tokenize text into a normalized sparse representation."""
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOPWORDS
    }


def tokenize_terms(text: str, *, expand_query: bool = False) -> list[str]:
    """Return frequency-preserving tokens for BM25 and reranking."""
    tokens = [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOPWORDS
    ]
    if expand_query:
        lowered = text.lower()
        for phrase, expansions in QUERY_EXPANSIONS.items():
            if phrase in lowered:
                tokens.extend(expansions)
    return tokens
