from __future__ import annotations

from app.agent.context import AgentContext, SessionRepository
from app.agent.trace import ReplayReader, TraceRepository
from app.agent.workflow import run_agent
from app.api.schemas import AgentQueryRequest, AgentQueryResponse
from evaluation.context_eval import run_context_evaluation


def _run(query, session_id, sessions, traces):
    return run_agent(
        query,
        persist_trajectory=False,
        session_id=session_id,
        session_repository=sessions,
        trace_repository=traces,
    )


def test_multi_turn_package_inheritance_and_parent_trace_chain():
    sessions = SessionRepository()
    traces = TraceRepository()

    first = _run("query openssl package info", "session-a", sessions, traces)
    second = _run("它的依赖是什么", "session-a", sessions, traces)
    third = _run("再比较版本", "session-a", sessions, traces)

    assert second["resolved_query"].startswith("openssl")
    assert second["inherited_context"] == {"package": "openssl"}
    assert "libssl.so" in second["answer"]
    assert "3.0.8" in third["answer"]
    assert second["parent_trace_id"] == first["trace_id"]
    assert third["parent_trace_id"] == second["trace_id"]


def test_explicit_entity_overrides_previous_context():
    sessions = SessionRepository()
    traces = TraceRepository()

    _run("query openssl package info", "override", sessions, traces)
    explicit = _run("query nginx package info", "override", sessions, traces)
    follow_up = _run("它的依赖", "override", sessions, traces)

    assert explicit["context"]["packages"][-1] == "nginx"
    assert follow_up["inherited_context"]["package"] == "nginx"
    assert "nginx depends on" in follow_up["answer"]


def test_sessions_are_isolated_and_clear_removes_context():
    sessions = SessionRepository()
    traces = TraceRepository()

    _run("query openssl package info", "isolated-a", sessions, traces)
    probe = _run("它的依赖是什么", "isolated-b", sessions, traces)

    assert probe["inherited_context"] == {}
    assert "openssl" not in probe["resolved_query"]
    assert sessions.clear("isolated-a") is True
    assert sessions.get("isolated-a") is None
    assert sessions.clear("isolated-a") is False


def test_session_repository_enforces_session_and_turn_capacity():
    repository = SessionRepository(max_sessions=2, max_turns=2)
    for session_id in ("one", "two", "three"):
        repository.save(AgentContext(session_id=session_id))

    assert repository.count() == 2
    assert repository.get("one") is None

    context = repository.get_or_create("three")
    context.recent_turns = [{"turn": index} for index in range(5)]
    repository.save(context)
    assert [item["turn"] for item in repository.get("three").recent_turns] == [3, 4]


def test_trace_is_complete_privacy_bounded_and_has_step_latency():
    result = _run("query tcpdump package info", "trace", SessionRepository(), TraceRepository())
    trace = result["trace"]

    assert trace["trace_schema_version"] == "trace-v1"
    assert trace["privacy"]["stores_internal_thought"] is False
    assert trace["metrics"]["trace_complete"] is True
    assert trace["policy_version"] == "deterministic-policy-v1"
    assert all("latency_ms" in step for step in trace["steps"])
    assert all("thought" not in step for step in trace["steps"])
    assert trace["output"]["verification"]["passed"] is True


def test_replay_reader_reconstructs_exact_inputs_and_replays_answer():
    sessions = SessionRepository()
    traces = TraceRepository()
    _run("query nginx package info", "replay", sessions, traces)
    follow_up = _run("它的依赖", "replay", sessions, traces)
    reader = ReplayReader(traces)

    reconstructed = reader.reconstruct(follow_up["trace_id"])
    replayed = reader.replay(follow_up["trace_id"], run_agent)

    assert reconstructed["original_query"] == "它的依赖"
    assert reconstructed["query"] == follow_up["resolved_query"]
    assert reconstructed["inherited_entities"] == {"package": "nginx"}
    assert reconstructed["reconstruction_complete"] is True
    assert replayed["answer"] == follow_up["answer"]
    assert replayed["replay_of"] == follow_up["trace_id"]


def test_trace_repository_capacity_and_jsonl_persistence(tmp_path):
    path = tmp_path / "traces.jsonl"
    traces = TraceRepository(path=path, max_records=2)
    records = []
    for index in range(3):
        record = {"trace_id": f"trace-{index}", "value": index}
        records.append(record)
        traces.save(record, persist=True)

    assert traces.count() == 2
    assert traces.get("trace-0") == records[0]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_api_schemas_accept_session_and_trace_additions():
    request = AgentQueryRequest(query="它的依赖", session_id="api-session")
    result = run_agent("query openssl package info", persist_trajectory=False)
    response = AgentQueryResponse(**result)

    assert request.session_id == "api-session"
    assert response.session_id
    assert response.trace_id
    assert response.trace_schema_version == "trace-v1"
    assert response.replayable is True


def test_context_trace_evaluation_meets_step_21_thresholds():
    report = run_context_evaluation()

    assert report["passed"]
    assert report["entity_consistency"] >= 0.95
    assert report["cross_session_leak_count"] == 0
    assert report["trace_completeness"] == 1.0
    assert report["replay_input_reconstruction"] == 1.0
    assert report["bad_cases"] == []
