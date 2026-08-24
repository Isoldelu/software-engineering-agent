"""Mine and cluster reproducible failures from offline labeled cases."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.agent.context import SessionRepository
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.evolution.models import FailureCluster, MinedFailure
from app.rag.retriever import DocumentRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGENT_CASES = PROJECT_ROOT / "evaluation" / "evolution_cases.json"
DEFAULT_RAG_CASES = PROJECT_ROOT / "evaluation" / "rag_cases.json"
GENERIC_ALIAS_TERMS = {
    "show", "query", "check", "find", "package", "metadata", "version", "info",
    "information", "details", "detail", "for", "the", "a", "an", "please",
}


class OfflineFailureMiner:
    def __init__(
        self,
        *,
        agent_cases_path: Path = DEFAULT_AGENT_CASES,
        rag_cases_path: Path = DEFAULT_RAG_CASES,
        minimum_cluster_support: int = 2,
    ) -> None:
        self.agent_cases_path = agent_cases_path
        self.rag_cases_path = rag_cases_path
        self.minimum_cluster_support = minimum_cluster_support

    def mine(self) -> tuple[list[MinedFailure], list[FailureCluster]]:
        failures = self._mine_agent_cases() + self._mine_rag_cases()
        grouped: dict[str, list[MinedFailure]] = defaultdict(list)
        for failure in failures:
            grouped[failure.cluster_key].append(failure)
        clusters = [
            self._build_cluster(key, items)
            for key, items in sorted(grouped.items())
            if len(items) >= self.minimum_cluster_support
        ]
        return failures, clusters

    def _mine_agent_cases(self) -> list[MinedFailure]:
        cases = json.loads(self.agent_cases_path.read_text(encoding="utf-8"))
        failures = []
        for index, case in enumerate(cases):
            result = run_agent(
                case["query"],
                persist_trajectory=False,
                session_id=f"evolution-mine-{index}",
                session_repository=SessionRepository(max_sessions=10),
                trace_repository=TraceRepository(max_records=10),
            )
            expected_tool = case["expected_tool"]
            expected_fragments = case.get("expected_answer_contains", [])
            if result["selected_tool"] != expected_tool:
                trigger = _routing_trigger(case["query"])
                failures.append(_failure(
                    source="agent_benchmark",
                    case=case,
                    issue_type="router_miss",
                    cluster_key=f"router:{expected_tool}:{trigger}",
                    expected={"tool": expected_tool, "answer_contains": expected_fragments},
                    observed={
                        "tool": result["selected_tool"],
                        "execution_status": result["execution_status"],
                        "answer": result["answer"],
                        "trace_id": result["trace_id"],
                    },
                    signal={"trigger": trigger, "tool": expected_tool},
                ))
                continue
            if not result["success"] or not all(
                fragment in result["answer"] for fragment in expected_fragments
            ):
                package = case.get("expected_package")
                if package:
                    alias = _alias_phrase(case["query"])
                    failures.append(_failure(
                        source="agent_benchmark",
                        case=case,
                        issue_type="entity_alias_miss",
                        cluster_key=f"alias:{package}:{alias}",
                        expected={
                            "tool": expected_tool,
                            "package": package,
                            "answer_contains": expected_fragments,
                        },
                        observed={
                            "tool": result["selected_tool"],
                            "execution_status": result["execution_status"],
                            "answer": result["answer"],
                            "trace_id": result["trace_id"],
                        },
                        signal={"alias": alias, "canonical_package": package},
                    ))
        return failures

    def _mine_rag_cases(self) -> list[MinedFailure]:
        cases = json.loads(self.rag_cases_path.read_text(encoding="utf-8"))
        retriever = DocumentRetriever(mode="legacy")
        failures = []
        for case in cases:
            relevant = set(case.get("relevant_chunk_ids", []))
            if not relevant:
                continue
            results = retriever.retrieve(
                case["query"],
                top_k=3,
                source_filter=case.get("source_filter"),
                version_filter=case.get("version_filter"),
            )
            retrieved = [item["chunk_id"] for item in results]
            if relevant & set(retrieved):
                continue
            failures.append(_failure(
                source="rag_benchmark",
                case=case,
                issue_type="retriever_rank_miss",
                cluster_key="retriever:legacy:recall_at_3",
                expected={"relevant_chunk_ids": sorted(relevant)},
                observed={"mode": "legacy", "retrieved_chunk_ids": retrieved},
                signal={
                    "mode": "hybrid",
                    "rrf_weight": 100.0,
                    "reranker_weight": 1.0,
                },
            ))
        return failures

    @staticmethod
    def _build_cluster(key: str, items: list[MinedFailure]) -> FailureCluster:
        issue_type = items[0].issue_type
        asset_type = {
            "router_miss": "router_rule",
            "entity_alias_miss": "query_alias",
            "retriever_rank_miss": "retriever_weights",
        }[issue_type]
        return FailureCluster(
            cluster_id=f"cluster_{_digest(key)}",
            issue_type=issue_type,
            cluster_key=key,
            failure_ids=[item.failure_id for item in items],
            support=len(items),
            candidate_asset_type=asset_type,
            signal=dict(items[0].candidate_signal),
        )


def _failure(
    *,
    source: str,
    case: dict[str, Any],
    issue_type: str,
    cluster_key: str,
    expected: dict[str, Any],
    observed: dict[str, Any],
    signal: dict[str, Any],
) -> MinedFailure:
    case_id = case["id"]
    return MinedFailure(
        failure_id=f"failure_{_digest(f'{source}:{case_id}:{issue_type}')}",
        source=source,
        case_id=case_id,
        query=case["query"],
        issue_type=issue_type,
        cluster_key=cluster_key,
        expected=expected,
        observed=observed,
        candidate_signal=signal,
    )


def _routing_trigger(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", query.lower())
    package_names = {"openssl", "ethtool", "nginx", "tcpdump"}
    remaining = [token for token in tokens if token not in package_names]
    return remaining[-1] if remaining else "unknown"


def _alias_phrase(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", query.lower())
    content = [token for token in tokens if token not in GENERIC_ALIAS_TERMS]
    return " ".join(content)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
