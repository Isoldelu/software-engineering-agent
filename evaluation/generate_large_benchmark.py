"""Generate a larger benchmark for Agent optimization experiments."""

from __future__ import annotations

import json
from pathlib import Path


OUTPUT_PATH = Path(__file__).resolve().parent / "large_benchmark.json"


PACKAGES = {
    "openssl": {
        "version": "3.0.8",
        "release": "1213",
        "dependencies": ["libssl.so", "libcrypto.so"],
        "changes": ["deprecated API", "encryption algorithm"],
        "aliases": ["secure communication library", "security library", "安全通信库"]
    },
    "ethtool": {
        "version": "5.15",
        "release": "1213",
        "dependencies": [],
        "changes": ["extended NIC diagnostics", "Ethernet link reporting"],
        "aliases": ["NIC diagnostics tool", "Ethernet tool", "网口诊断工具"]
    },
    "nginx": {
        "version": "1.24",
        "release": "1214",
        "dependencies": ["openssl", "libhttp.so"],
        "changes": ["HTTP performance", "openssl"],
        "aliases": ["management-plane web service", "web service", "管理面 web"]
    },
    "tcpdump": {
        "version": "4.99",
        "release": "1214",
        "dependencies": ["libpcap.so"],
        "changes": ["packet capture filter compatibility", "libpcap.so"],
        "aliases": ["packet capture tool", "capture tool", "抓包工具"]
    }
}

COMPONENTS = {
    "libssl.so": "openssl",
    "libcrypto.so": "openssl",
    "ethtool": "ethtool",
    "nginx": "nginx",
    "libhttp.so": "nginx",
    "tcpdump": "tcpdump",
    "libpcap.so": "tcpdump"
}


def main() -> None:
    cases = []
    cases.extend(_package_cases())
    cases.extend(_dependency_cases())
    cases.extend(_version_cases())
    cases.extend(_component_cases())
    cases.extend(_rag_cases())
    cases.extend(_hybrid_cases())
    OUTPUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUTPUT_PATH}")


def _package_cases() -> list[dict]:
    templates = [
        "query {package} version",
        "show package metadata for {package}",
        "what release contains {package}",
        "查询 {package} 的版本",
        "{alias} package info",
        "release {release} package list",
        "{release} 版本有哪些软件包",
        "which files are included in {package}"
    ]
    cases = []
    for index in range(30):
        package, data = _package_at(index)
        query = _format(templates[index % len(templates)], package, data)
        expected = [package, data["version"]] if "release {release}" not in templates[index % len(templates)] and "版本有哪些" not in templates[index % len(templates)] else [data["release"]]
        if "files" in query:
            expected = [package]
        cases.append(_case("package_query", query, expected_tool="package_search", expected_answer_contains=expected))
    return cases


def _dependency_cases() -> list[dict]:
    templates = [
        "{package} dependencies",
        "what does {package} depend on",
        "查看 {package} 依赖",
        "{alias} depends on what",
        "{package} requires which components",
        "dependency tree for {package}"
    ]
    cases = []
    packages = ["openssl", "nginx", "tcpdump"]
    for index in range(30):
        package = packages[index % len(packages)]
        data = PACKAGES[package]
        query = _format(templates[index % len(templates)], package, data)
        expected = [package, data["dependencies"][0]]
        cases.append(_case("dependency", query, expected_tool="dependency_analysis", expected_answer_contains=expected))
    return cases


def _version_cases() -> list[dict]:
    templates = [
        "compare {package} version changes",
        "what changed after {package} upgrade",
        "{package} upgrade impact",
        "查看 {package} 版本变化",
        "{alias} 升级后有什么变化",
        "{package} changed from old version to new version"
    ]
    cases = []
    for index in range(30):
        package, data = _package_at(index)
        query = _format(templates[index % len(templates)], package, data)
        expected = [package, data["changes"][0]]
        cases.append(_case("version_compare", query, expected_tool="version_compare", expected_answer_contains=expected))
    return cases


def _component_cases() -> list[dict]:
    templates = [
        "which package owns {component}",
        "{component} belongs to which package",
        "{component} 属于哪个软件包",
        "owner package for {component}"
    ]
    cases = []
    items = list(COMPONENTS.items())
    for index in range(20):
        component, package = items[index % len(items)]
        query = templates[index % len(templates)].format(component=component)
        cases.append(_case("component_mapping", query, expected_tool="component_mapping", expected_answer_contains=[component, package]))
    return cases


def _rag_cases() -> list[dict]:
    templates = [
        "release note says what was added in 1214",
        "software manual describes tcpdump as what",
        "according to release note, what is in 1213",
        "manual explains openssl as what",
        "1214 发布说明新增了什么",
        "文档里 tcpdump 是做什么的"
    ]
    expected_options = [
        ["Release 1214", "nginx", "tcpdump"],
        ["tcpdump", "packet capture"],
        ["Release 1213", "openssl", "ethtool"],
        ["openssl", "secure communication"],
        ["Release 1214", "tcpdump"],
        ["tcpdump", "packet capture"]
    ]
    cases = []
    for index in range(30):
        query = templates[index % len(templates)]
        expected = expected_options[index % len(expected_options)]
        cases.append(_case("rag_query", query, expected_tool="rag_retrieval", expected_answer_contains=expected))
    return cases


def _hybrid_cases() -> list[dict]:
    templates = [
        "1214 release packages and their dependencies",
        "according to release note, what dependencies do tcpdump have in 1214",
        "1214 release packages and their version changes",
        "查一下 nginx 的版本变化和依赖",
        "1213 release packages and their dependencies",
        "1214 里面抓包工具升级了啥"
    ]
    expected_tools = [
        ["rag_retrieval", "package_search", "dependency_analysis", "dependency_analysis"],
        ["rag_retrieval", "package_search", "dependency_analysis"],
        ["rag_retrieval", "package_search", "version_compare", "version_compare"],
        ["package_search", "dependency_analysis", "version_compare"],
        ["rag_retrieval", "package_search", "dependency_analysis", "dependency_analysis"],
        ["rag_retrieval", "package_search", "version_compare"]
    ]
    expected_options = [
        ["Release 1214", "nginx", "tcpdump", "libpcap.so"],
        ["tcpdump", "libpcap.so"],
        ["nginx", "tcpdump", "packet capture filter compatibility"],
        ["nginx", "openssl", "HTTP performance"],
        ["Release 1213", "openssl", "ethtool"],
        ["tcpdump", "4.99"]
    ]
    cases = []
    for index in range(30):
        position = index % len(templates)
        cases.append(_case(
            "hybrid_task",
            templates[position],
            expected_tools=expected_tools[position],
            expected_answer_contains=expected_options[position]
        ))
    return cases


def _case(
    category: str,
    query: str,
    expected_answer_contains: list[str],
    expected_tool: str | None = None,
    expected_tools: list[str] | None = None
) -> dict:
    item = {
        "category": category,
        "query": query,
        "expected_answer_contains": expected_answer_contains
    }
    if expected_tools:
        item["expected_tools"] = expected_tools
    else:
        item["expected_tool"] = expected_tool
    return item


def _package_at(index: int) -> tuple[str, dict]:
    package = list(PACKAGES)[index % len(PACKAGES)]
    return package, PACKAGES[package]


def _format(template: str, package: str, data: dict) -> str:
    return template.format(
        package=package,
        release=data["release"],
        alias=data["aliases"][0]
    )


if __name__ == "__main__":
    main()
