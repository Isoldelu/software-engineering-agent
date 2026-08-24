"""Generate and shadow-evaluate safe offline configuration candidates."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.agent.context import SessionRepository
from app.agent.router import extract_component, extract_package, extract_release
from app.agent.trace import TraceRepository
from app.agent.workflow import run_agent
from app.evolution.models import EvolutionCandidate, FailureCluster, MinedFailure
from app.rag.retriever import DocumentRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGRESSION_CASE_PATHS = [
    PROJECT_ROOT / "evaluation" / "test_cases.json",
    PROJECT_ROOT / "evaluation" / "challenge_cases.json",
    PROJECT_ROOT / "evaluation" / "robustness_cases.json",
    PROJECT_ROOT / "evaluation" / "large_benchmark.json",
]
RAG_CASES_PATH = PROJECT_ROOT / "evaluation" / "rag_cases.json"


class EvolutionCandidateFactory:
    def build(self, cluster: FailureCluster, *, created_at: str) -> EvolutionCandidate:
        signal = cluster.signal
        config: dict[str, Any]
        if cluster.candidate_asset_type == "router_rule":
            tool = signal["tool"]
            config = {
                "rules": [{
                    "hook_id": f"offline_{signal['trigger']}_{tool}",
                    "match": {"terms": [signal["trigger"]], "mode": "any"},
                    "action": {"intent": tool, "tool": tool},
                    "priority": 90,
                }]
            }
        elif cluster.candidate_asset_type == "query_alias":
            config = {
                "aliases": {
                    signal["alias"]: signal["canonical_package"],
                }
            }
        else:
            config = {
                "mode": signal["mode"],
                "rrf_weight": signal["rrf_weight"],
                "reranker_weight": signal["reranker_weight"],
            }
        return EvolutionCandidate(
            candidate_id=f"evo_{cluster.cluster_id.removeprefix('cluster_')}",
            schema_version="evolution-candidate-v1",
            asset_type=cluster.candidate_asset_type,
            status="draft",
            source_cluster_id=cluster.cluster_id,
            source_failure_ids=list(cluster.failure_ids),
            config=config,
            safety_scope={
                "allowed_changes": [cluster.candidate_asset_type],
                "forbidden_changes": [
                    "python_source",
                    "datasets",
                    "test_assertions",
                    "permissions",
                    "release_gates",
                ],
                "automatic_activation": False,
                "requires_human_review": True,
            },
            created_at=created_at,
        )


class EvolutionConfigValidator:
    def validate(self, candidate: EvolutionCandidate) -> list[str]:
        issues = []
        if candidate.asset_type not in {"router_rule", "query_alias", "retriever_weights"}:
            issues.append("unsupported_asset_type")
        if candidate.safety_scope.get("automatic_activation") is not False:
            issues.append("automatic_activation_not_blocked")
        if candidate.safety_scope.get("requires_human_review") is not True:
            issues.append("human_review_not_required")
        forbidden = set(candidate.safety_scope.get("forbidden_changes", []))
        required = {"python_source", "datasets", "test_assertions", "permissions", "release_gates"}
        if not required <= forbidden:
            issues.append("incomplete_forbidden_scope")
        if candidate.asset_type == "router_rule":
            rules = candidate.config.get("rules", [])
            if not isinstance(rules, list) or len(rules) != 1:
                issues.append("invalid_router_rules")
        elif candidate.asset_type == "query_alias":
            aliases = candidate.config.get("aliases", {})
            if not isinstance(aliases, dict) or len(aliases) != 1:
                issues.append("invalid_aliases")
        elif candidate.asset_type == "retriever_weights":
            if candidate.config.get("mode") != "hybrid":
                issues.append("invalid_retrieval_mode")
            for key in ("rrf_weight", "reranker_weight"):
                value = candidate.config.get(key)
                if not isinstance(value, (int, float)) or value < 0 or value > 1000:
                    issues.append(f"invalid_{key}")
        return sorted(set(issues))


class ShadowCandidateRunner:
    def __init__(self, candidate: EvolutionCandidate) -> None:
        self.candidate = candidate

    def run_agent_case(self, query: str) -> dict[str, Any]:
        effective_query = query
        plan_output = None
        if self.candidate.asset_type == "query_alias":
            for alias, canonical in self.candidate.config["aliases"].items():
                effective_query = effective_query.replace(alias, canonical)
        elif self.candidate.asset_type == "router_rule":
            plan = self._matching_plan(query)
            plan_output = json.dumps(plan) if plan else None
        return run_agent(
            effective_query,
            persist_trajectory=False,
            llm_plan_output=plan_output,
            session_repository=SessionRepository(max_sessions=5),
            trace_repository=TraceRepository(max_records=10),
        )

    def retrieve(self, failure: MinedFailure) -> list[dict[str, Any]]:
        config = self.candidate.config
        retriever = DocumentRetriever(
            mode=config["mode"],
            hybrid_weights={
                "rrf_weight": config["rrf_weight"],
                "reranker_weight": config["reranker_weight"],
            },
        )
        return retriever.retrieve(failure.query, top_k=3)

    def _matching_plan(self, query: str) -> dict[str, Any] | None:
        lowered = query.lower()
        rule = self.candidate.config["rules"][0]
        if not any(term.lower() in lowered for term in rule["match"]["terms"]):
            return None
        action = rule["action"]
        arguments = {
            "package": extract_package(lowered),
            "release": extract_release(lowered),
            "component": extract_component(lowered),
            "query": query,
        }
        return {
            "intent": action["intent"],
            "tool": action["tool"],
            "arguments": arguments,
            "confidence": "high",
            "reason": "Matched an isolated offline evolution candidate.",
            "steps": [{
                "tool": action["tool"],
                "arguments": arguments,
                "reason": "Shadow candidate tool selection.",
            }],
        }


class ShadowEvaluator:
    def evaluate(
        self,
        candidate: EvolutionCandidate,
        failures: list[MinedFailure],
    ) -> dict[str, Any]:
        issues = EvolutionConfigValidator().validate(candidate)
        if issues:
            return {
                "schema_version": "shadow-eval-v1",
                "config_issues": issues,
                "passed": False,
                "next_status": "rejected",
                "gates": {"configuration_scope_valid": False},
            }
        linked = [item for item in failures if item.failure_id in candidate.source_failure_ids]
        if candidate.asset_type == "retriever_weights":
            return self._evaluate_retriever(candidate, linked)
        return self._evaluate_agent_config(candidate, linked)

    def _evaluate_agent_config(
        self,
        candidate: EvolutionCandidate,
        linked: list[MinedFailure],
    ) -> dict[str, Any]:
        runner = ShadowCandidateRunner(candidate)
        linked_results = []
        for failure in linked:
            baseline = _run_agent(failure.query)
            shadow = runner.run_agent_case(failure.query)
            baseline_passed = _agent_failure_passed(failure, baseline)
            shadow_passed = _agent_failure_passed(failure, shadow)
            linked_results.append({
                "failure_id": failure.failure_id,
                "case_id": failure.case_id,
                "query": failure.query,
                "baseline_passed": baseline_passed,
                "shadow_passed": shadow_passed,
                "fixed": not baseline_passed and shadow_passed,
            })

        cases = [
            case
            for path in REGRESSION_CASE_PATHS
            for case in json.loads(path.read_text(encoding="utf-8"))
        ]
        regressions = []
        baseline_latencies = []
        shadow_latencies = []
        baseline_pass_count = 0
        shadow_pass_count = 0
        for case in cases:
            baseline = _run_agent(case["query"])
            shadow = runner.run_agent_case(case["query"])
            baseline_passed = _agent_case_passed(case, baseline)
            shadow_passed = _agent_case_passed(case, shadow)
            baseline_pass_count += baseline_passed
            shadow_pass_count += shadow_passed
            baseline_latencies.append(baseline["trace"]["metrics"]["total_latency_ms"])
            shadow_latencies.append(shadow["trace"]["metrics"]["total_latency_ms"])
            if baseline_passed and not shadow_passed:
                regressions.append({"query": case["query"], "category": case.get("category")})
        return _shadow_report(
            candidate=candidate,
            linked_results=linked_results,
            regression_count=len(cases),
            regressions=regressions,
            baseline_score=baseline_pass_count / len(cases),
            shadow_score=shadow_pass_count / len(cases),
            baseline_latency_ms=statistics.mean(baseline_latencies),
            shadow_latency_ms=statistics.mean(shadow_latencies),
        )

    def _evaluate_retriever(
        self,
        candidate: EvolutionCandidate,
        linked: list[MinedFailure],
    ) -> dict[str, Any]:
        runner = ShadowCandidateRunner(candidate)
        baseline_retriever = DocumentRetriever(mode="legacy")
        linked_results = []
        for failure in linked:
            baseline_ids = [
                item["chunk_id"] for item in baseline_retriever.retrieve(failure.query, top_k=3)
            ]
            started = time.perf_counter()
            shadow_ids = [item["chunk_id"] for item in runner.retrieve(failure)]
            latency = (time.perf_counter() - started) * 1000
            relevant = set(failure.expected["relevant_chunk_ids"])
            baseline_passed = bool(relevant & set(baseline_ids))
            shadow_passed = bool(relevant & set(shadow_ids))
            linked_results.append({
                "failure_id": failure.failure_id,
                "case_id": failure.case_id,
                "query": failure.query,
                "baseline_passed": baseline_passed,
                "shadow_passed": shadow_passed,
                "fixed": not baseline_passed and shadow_passed,
                "shadow_latency_ms": latency,
            })

        cases = json.loads(RAG_CASES_PATH.read_text(encoding="utf-8"))
        shadow_retriever = DocumentRetriever(
            mode="hybrid",
            hybrid_weights={
                "rrf_weight": candidate.config["rrf_weight"],
                "reranker_weight": candidate.config["reranker_weight"],
            },
        )
        regressions = []
        baseline_pass_count = 0
        shadow_pass_count = 0
        baseline_latencies = []
        shadow_latencies = []
        for case in cases:
            started = time.perf_counter()
            baseline = baseline_retriever.retrieve(
                case["query"], top_k=3,
                source_filter=case.get("source_filter"),
                version_filter=case.get("version_filter"),
            )
            baseline_latencies.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            shadow = shadow_retriever.retrieve(
                case["query"], top_k=3,
                source_filter=case.get("source_filter"),
                version_filter=case.get("version_filter"),
            )
            shadow_latencies.append((time.perf_counter() - started) * 1000)
            relevant = set(case.get("relevant_chunk_ids", []))
            regression_baseline_ids = {item["chunk_id"] for item in baseline}
            regression_shadow_ids = {item["chunk_id"] for item in shadow}
            baseline_passed = (
                bool(relevant & regression_baseline_ids)
                if relevant else not regression_baseline_ids
            )
            shadow_passed = (
                bool(relevant & regression_shadow_ids)
                if relevant else not regression_shadow_ids
            )
            baseline_pass_count += baseline_passed
            shadow_pass_count += shadow_passed
            if baseline_passed and not shadow_passed:
                regressions.append({"query": case["query"], "id": case["id"]})
        return _shadow_report(
            candidate=candidate,
            linked_results=linked_results,
            regression_count=len(cases),
            regressions=regressions,
            baseline_score=baseline_pass_count / len(cases),
            shadow_score=shadow_pass_count / len(cases),
            baseline_latency_ms=statistics.mean(baseline_latencies),
            shadow_latency_ms=statistics.mean(shadow_latencies),
        )


def _run_agent(query: str) -> dict[str, Any]:
    return run_agent(
        query,
        persist_trajectory=False,
        session_repository=SessionRepository(max_sessions=5),
        trace_repository=TraceRepository(max_records=10),
    )


def _agent_failure_passed(failure: MinedFailure, result: dict[str, Any]) -> bool:
    return (
        result["selected_tool"] == failure.expected["tool"]
        and result["success"]
        and all(
            fragment in result["answer"]
            for fragment in failure.expected.get("answer_contains", [])
        )
    )


def _agent_case_passed(case: dict[str, Any], result: dict[str, Any]) -> bool:
    if "expected_tools" in case:
        tool_correct = result.get("used_tools", []) == case["expected_tools"]
    else:
        tool_correct = result["selected_tool"] == case["expected_tool"]
    expected_status = case.get("expected_status", "success")
    statuses = [
        item.get("observation", {}).get("status")
        for item in result.get("trajectory", [])
        if item.get("stage") == "tool_execution"
    ]
    status_correct = (
        "not_found" in statuses if expected_status == "not_found" else result["success"]
    )
    answer_correct = all(
        fragment in result["answer"] for fragment in case.get("expected_answer_contains", [])
    )
    return tool_correct and status_correct and answer_correct


def _shadow_report(
    *,
    candidate: EvolutionCandidate,
    linked_results: list[dict[str, Any]],
    regression_count: int,
    regressions: list[dict[str, Any]],
    baseline_score: float,
    shadow_score: float,
    baseline_latency_ms: float,
    shadow_latency_ms: float,
) -> dict[str, Any]:
    fixed_count = sum(item["fixed"] for item in linked_results)
    linked_baseline = sum(item["baseline_passed"] for item in linked_results)
    linked_shadow = sum(item["shadow_passed"] for item in linked_results)
    linked_count = len(linked_results)
    gates = {
        "configuration_scope_valid": True,
        "linked_score_improved": linked_shadow > linked_baseline,
        "fixed_at_least_two": fixed_count >= 2,
        "regressed_cases_zero": not regressions,
        "core_score_not_decreased": shadow_score >= baseline_score,
        "automatic_activation_blocked": candidate.safety_scope["automatic_activation"] is False,
        "human_review_required": candidate.safety_scope["requires_human_review"] is True,
    }
    return {
        "schema_version": "shadow-eval-v1",
        "candidate_id": candidate.candidate_id,
        "asset_type": candidate.asset_type,
        "linked_case_count": linked_count,
        "linked_baseline_score": linked_baseline / linked_count if linked_count else 1.0,
        "linked_shadow_score": linked_shadow / linked_count if linked_count else 1.0,
        "fixed_bad_case_count": fixed_count,
        "regression_case_count": regression_count,
        "regressed_case_count": len(regressions),
        "regressed_cases": regressions,
        "baseline_core_score": baseline_score,
        "shadow_core_score": shadow_score,
        "baseline_latency_ms": baseline_latency_ms,
        "shadow_latency_ms": shadow_latency_ms,
        "added_latency_ms": max(0.0, shadow_latency_ms - baseline_latency_ms),
        "linked_results": linked_results,
        "gates": gates,
        "passed": all(gates.values()),
        "next_status": "pending_review" if all(gates.values()) else "rejected",
    }
