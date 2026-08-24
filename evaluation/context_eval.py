"""Evaluate multi-turn entity consistency, session isolation, and Trace replay."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_CASES_PATH = PROJECT_ROOT / "evaluation" / "context_cases.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.context import SessionRepository
from app.agent.trace import ReplayReader, TraceRepository
from app.agent.workflow import run_agent


def run_context_evaluation(cases_path: Path = CONTEXT_CASES_PATH) -> dict[str, Any]:
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    conversation_results = [
        _evaluate_conversation(case)
        for case in document["conversations"]
    ]
    isolation_results = [
        _evaluate_isolation(case, index)
        for index, case in enumerate(document["isolation_cases"], start=1)
    ]
    turns = [turn for case in conversation_results for turn in case["turns"]]
    follow_ups = [turn for turn in turns if turn["expected_inherited"]]
    entity_consistency = _ratio(
        sum(1 for turn in follow_ups if turn["entity_consistent"]),
        len(follow_ups),
    )
    trace_completeness = _ratio(
        sum(1 for turn in turns if turn["trace_complete"]),
        len(turns),
    )
    replay_reconstruction = _ratio(
        sum(1 for turn in turns if turn["replay_reconstructed"]),
        len(turns),
    )
    cross_session_leaks = sum(1 for item in isolation_results if item["leaked"])
    thresholds = {
        "entity_consistency": entity_consistency >= 0.95,
        "cross_session_leakage": cross_session_leaks == 0,
        "trace_completeness": trace_completeness == 1.0,
        "replay_input_reconstruction": replay_reconstruction == 1.0,
    }
    return {
        "benchmark": "Software-Agent-Context-Trace",
        "conversation_count": len(conversation_results),
        "turn_count": len(turns),
        "follow_up_count": len(follow_ups),
        "entity_consistency": entity_consistency,
        "cross_session_leak_count": cross_session_leaks,
        "cross_session_leakage_rate": _ratio(cross_session_leaks, len(isolation_results)),
        "trace_completeness": trace_completeness,
        "replay_input_reconstruction": replay_reconstruction,
        "thresholds": thresholds,
        "passed": all(thresholds.values()),
        "bad_cases": [
            turn for turn in turns
            if not turn["entity_consistent"] or not turn["answer_correct"]
            or not turn["trace_complete"] or not turn["replay_reconstructed"]
        ] + [item for item in isolation_results if item["leaked"]],
        "conversations": conversation_results,
        "isolation_results": isolation_results,
    }


def _evaluate_conversation(case: dict[str, Any]) -> dict[str, Any]:
    sessions = SessionRepository(max_sessions=10, max_turns=10)
    traces = TraceRepository(max_records=50)
    session_id = f"eval-{case['id']}"
    turn_results = []
    for index, turn in enumerate(case["turns"], start=1):
        result = run_agent(
            turn["query"],
            persist_trajectory=False,
            session_id=session_id,
            session_repository=sessions,
            trace_repository=traces,
        )
        expected = turn.get("expected_inherited", {})
        inherited = result.get("inherited_context", {})
        replay = ReplayReader(traces).reconstruct(result["trace_id"])
        turn_results.append({
            "conversation_id": case["id"],
            "turn": index,
            "query": turn["query"],
            "resolved_query": result["resolved_query"],
            "expected_inherited": expected,
            "inherited_context": inherited,
            "entity_consistent": all(inherited.get(key) == value for key, value in expected.items()),
            "answer_correct": all(fragment in result["answer"] for fragment in turn.get("answer_contains", [])),
            "trace_complete": _trace_complete(result["trace"]),
            "replay_reconstructed": bool(
                replay
                and replay["reconstruction_complete"]
                and replay["query"] == result["resolved_query"]
                and replay["original_query"] == result["query"]
            ),
            "trace_id": result["trace_id"],
            "parent_trace_id": result["parent_trace_id"],
            "answer": result["answer"],
        })
    return {"id": case["id"], "turns": turn_results}


def _evaluate_isolation(case: dict[str, Any], index: int) -> dict[str, Any]:
    sessions = SessionRepository(max_sessions=10)
    traces = TraceRepository(max_records=20)
    run_agent(
        case["seed_query"], False, session_id=f"iso-a-{index}",
        session_repository=sessions, trace_repository=traces,
    )
    probe = run_agent(
        case["probe_query"], False, session_id=f"iso-b-{index}",
        session_repository=sessions, trace_repository=traces,
    )
    forbidden = case["forbidden_entity"]
    leaked = (
        probe.get("inherited_context", {}).get("package") == forbidden
        or forbidden in probe["resolved_query"].lower()
    )
    return {
        "seed_query": case["seed_query"],
        "probe_query": case["probe_query"],
        "forbidden_entity": forbidden,
        "probe_resolved_query": probe["resolved_query"],
        "inherited_context": probe["inherited_context"],
        "leaked": leaked,
    }


def _trace_complete(trace: dict[str, Any]) -> bool:
    required = {
        "trace_schema_version", "trace_id", "session_id", "created_at",
        "policy_version", "input", "plan", "steps", "output", "metrics", "privacy",
    }
    return (
        required <= trace.keys()
        and trace["metrics"].get("trace_complete") is True
        and trace["privacy"].get("stores_internal_thought") is False
        and not _contains_internal_thought_field(trace)
        and all("latency_ms" in step for step in trace["steps"])
    )


def _contains_internal_thought_field(value: Any) -> bool:
    if isinstance(value, dict):
        return "thought" in value or any(
            _contains_internal_thought_field(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_internal_thought_field(item) for item in value)
    return False


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


if __name__ == "__main__":
    print(json.dumps(run_context_evaluation(), ensure_ascii=False, indent=2))
