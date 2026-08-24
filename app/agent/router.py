"""Agent router.

Step 3 uses a deterministic intent router as a local stand-in for an LLM Router.
It returns both the selected tool and extracted arguments so the workflow can
execute a complete Agent loop.
"""

from __future__ import annotations

import re


PACKAGE_NAMES = ("openssl", "ethtool", "nginx", "tcpdump")
COMPONENT_NAMES = ("libssl.so", "libcrypto.so", "ethtool", "nginx", "libhttp.so", "tcpdump", "libpcap.so")
PACKAGE_ALIASES = {
    "openssl": (
        "secure communication",
        "security library",
        "crypto library",
        "ssl library",
        "\u5b89\u5168\u901a\u4fe1\u5e93",
        "\u52a0\u5bc6\u5e93",
        "\u5b89\u5168\u5e93",
    ),
    "tcpdump": (
        "packet capture",
        "capture tool",
        "\u6293\u5305",
        "\u6293\u5305\u5de5\u5177",
        "\u6d41\u91cf\u5206\u6790",
    ),
    "ethtool": (
        "ethernet",
        "nic",
        "link diagnostics",
        "\u7f51\u53e3",
        "\u7f51\u5361",
        "\u7f51\u53e3\u8bca\u65ad",
        "\u8bca\u65ad\u5de5\u5177",
    ),
    "nginx": (
        "web service",
        "management-plane web",
        "management plane web",
        "\u7ba1\u7406\u9762 web",
        "\u7ba1\u7406\u9762web",
        "web\u670d\u52a1",
    ),
}

DEPENDENCY_KEYWORDS = (
    "\u4f9d\u8d56",  # dependency
    "dependency",
    "dependencies",
    "depends",
    "depend on",
    "requires",
    "require",
    "\u5f15\u5165",  # introduce
    "\u8c01\u4f9d\u8d56",  # who depends on
)

VERSION_COMPARE_KEYWORDS = (
    "\u6bd4\u8f83",  # compare
    "\u53d8\u5316",  # change
    "\u53d8\u66f4",  # change
    "\u5347\u7ea7",  # upgrade
    "compare",
    "changed",
    "change",
    "upgrade",
    "from",
    "\u6539\u4e86\u5565",  # what changed
    "\u6539\u4e86\u4ec0\u4e48",  # what changed
    "\u5347\u7ea7\u4e86\u5565",  # what was upgraded
)

RAG_RETRIEVAL_KEYWORDS = (
    "\u6587\u6863",  # document
    "\u624b\u518c",  # manual
    "\u8bf4\u660e",  # description/manual
    "\u53d1\u5e03\u8bf4\u660e",  # release note
    "\u53d1\u5e03\u8bb0\u5f55",  # release record
    "document",
    "docs",
    "manual",
    "release note",
    "note",
    "describe",
    "describes",
    "according to",
    "release",
    "\u53d1\u5e03",  # release
)

COMPONENT_MAPPING_KEYWORDS = (
    "\u5c5e\u4e8e",  # belong to
    "\u5f52\u5c5e",  # ownership
    "\u54ea\u4e2a\u8f6f\u4ef6\u5305",  # which package
    "\u54ea\u4e2a package",
    "belong",
    "belongs",
    "owner",
    "owns",
    "contain",
    "contains",
    "which package",
)


def route_query(query: str) -> str:
    """Return the selected tool name for backward compatibility."""
    return route_query_detail(query)["tool"]


def route_query_detail(query: str) -> dict:
    """Classify intent, select a tool, and extract simple tool arguments."""
    normalized = query.lower()
    package = extract_package(normalized)
    release = extract_release(normalized)
    component = extract_component(normalized)

    if _is_release_contains_query(query, normalized):
        return {
            "intent": "package_search",
            "tool": "package_search",
            "arguments": {
                "package": package,
                "release": release
            },
            "confidence": "high" if package or release else "medium",
            "reason": "The query asks which release or package list contains a package."
        }

    if component and _contains_any(query, normalized, DEPENDENCY_KEYWORDS):
        return {
            "intent": "dependency_analysis",
            "tool": "dependency_analysis",
            "arguments": {"package": package, "component": component},
            "confidence": "high",
            "reason": "The query asks which package depends on a component."
        }

    if component and (
        _contains_any(query, normalized, COMPONENT_MAPPING_KEYWORDS)
        or not package
    ):
        return {
            "intent": "component_mapping",
            "tool": "component_mapping",
            "arguments": {"component": component},
            "confidence": "high",
            "reason": "The query asks which package owns a component or file."
        }

    if _is_package_metadata_query(query, normalized):
        return {
            "intent": "package_search",
            "tool": "package_search",
            "arguments": {
                "package": package,
                "release": release
            },
            "confidence": "high" if package or release else "medium",
            "reason": "The query asks for package metadata or release package lists."
        }

    if _contains_any(query, normalized, RAG_RETRIEVAL_KEYWORDS):
        return {
            "intent": "doc_retrieval",
            "tool": "rag_retrieval",
            "arguments": {
                "package": package,
                "release": release,
                "component": component
            },
            "confidence": "high",
            "reason": "The query asks for evidence from release notes or manuals."
        }

    if _contains_any(query, normalized, DEPENDENCY_KEYWORDS):
        return {
            "intent": "dependency_analysis",
            "tool": "dependency_analysis",
            "arguments": {"package": package},
            "confidence": "high" if package else "medium",
            "reason": "The query asks about package dependencies."
        }

    if _contains_any(query, normalized, VERSION_COMPARE_KEYWORDS):
        return {
            "intent": "version_compare",
            "tool": "version_compare",
            "arguments": {"package": package},
            "confidence": "high" if package else "medium",
            "reason": "The query asks about version changes or comparison."
        }

    return {
        "intent": "package_search",
        "tool": "package_search",
        "arguments": {
            "package": package,
            "release": release
        },
        "confidence": "high" if package or release else "medium",
        "reason": "The query asks for package or release metadata."
    }


def extract_package(normalized_query: str) -> str | None:
    """Extract a known simulated package name from the query."""
    for package in PACKAGE_NAMES:
        if package in normalized_query:
            return package
    for package, aliases in PACKAGE_ALIASES.items():
        if any(alias in normalized_query for alias in aliases):
            return package
    return None


def extract_release(normalized_query: str) -> str | None:
    """Extract a four-digit release id from the query."""
    match = re.search(r"\b\d{4}\b", normalized_query)
    return match.group(0) if match else None


def extract_component(normalized_query: str) -> str | None:
    """Extract a known component or file-like token from the query."""
    for component in COMPONENT_NAMES:
        if component in normalized_query:
            return component
    match = re.search(r"[\w.-]+\.(?:so|ko|bin|conf|service|rpm)", normalized_query)
    return match.group(0) if match else None


def _contains_any(original_query: str, normalized_query: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in original_query or keyword in normalized_query for keyword in keywords)


def _is_package_metadata_query(original_query: str, normalized_query: str) -> bool:
    package_patterns = (
        "package info",
        "package metadata",
        "package list",
        "what release contains",
        "which release contains",
        "\u8f6f\u4ef6\u5305",
        "\u54ea\u4e9b\u8f6f\u4ef6",
    )
    return any(pattern in original_query or pattern in normalized_query for pattern in package_patterns)


def _is_release_contains_query(original_query: str, normalized_query: str) -> bool:
    patterns = (
        "what release contains",
        "which release contains",
        "release contains",
        "release package list",
        "package list",
    )
    return any(pattern in original_query or pattern in normalized_query for pattern in patterns)
