"""Agent workflow.

The Step 3 workflow executes a minimal Agent loop:

query -> route -> tool call -> observation -> structured answer -> trajectory
"""

from __future__ import annotations

import json
import time

from app.agent.context import (
    DEFAULT_SESSION_REPOSITORY,
    ContextResolver,
    SessionRepository,
)
from app.agent.memory import TrajectoryMemory
from app.agent.planner import build_plan
from app.agent.router import route_query, route_query_detail
from app.agent.verifier import DeterministicVerifier, aggregate_execution_status
from app.agent.trace import (
    DEFAULT_TRACE_REPOSITORY,
    ReplayReader,
    TraceRecorder,
    TraceRepository,
    utc_now,
)
from app.evidence.normalizer import citations_from_evidence
from app.policy.engine import DEFAULT_POLICY_ENGINE, PolicyEngine
from app.tools.component_tool import ComponentMappingTool
from app.tools.dependency_tool import DependencyAnalysisTool
from app.tools.package_tool import PackageSearchTool
from app.tools.rag_tool import RAGRetrieverTool
from app.tools.version_tool import VersionCompareTool


TOOL_REGISTRY = {
    ComponentMappingTool.name: ComponentMappingTool,
    PackageSearchTool.name: PackageSearchTool,
    DependencyAnalysisTool.name: DependencyAnalysisTool,
    RAGRetrieverTool.name: RAGRetrieverTool,
    VersionCompareTool.name: VersionCompareTool,
}


def preview_workflow(query: str) -> dict:
    """Preview the router decision without executing tools."""
    route = route_query_detail(query)
    return {
        "query": query,
        "selected_tool": route["tool"],
        "route": route,
        "status": "tool_execution_available"
    }


def run_workflow(query: str) -> dict:
    """Route a query to a deterministic tool and return the observation."""
    selected_tool = route_query(query)
    tool_class = TOOL_REGISTRY[selected_tool]
    tool = tool_class()
    observation = tool.run(query)

    return {
        "query": query,
        "selected_tool": selected_tool,
        "observation": observation
    }


def run_agent(
    query: str,
    persist_trajectory: bool = True,
    llm_plan_output: str | None = None,
    session_id: str | None = None,
    session_repository: SessionRepository | None = None,
    trace_repository: TraceRepository | None = None,
    policy_engine: PolicyEngine | None = None,
    planner_metadata: dict | None = None,
) -> dict:
    """Run the complete Agent flow."""
    started_clock = time.perf_counter()
    started_at = utc_now()
    sessions = session_repository or DEFAULT_SESSION_REPOSITORY
    traces = trace_repository or DEFAULT_TRACE_REPOSITORY
    policies = policy_engine or DEFAULT_POLICY_ENGINE
    context_resolver = ContextResolver()
    context = sessions.get_or_create(session_id)
    parent_trace_id = context.last_trace_id
    resolved_query, inherited_entities = context_resolver.resolve(query, context)
    trace_id = traces.new_trace_id()
    policy_assignment = policies.assign(context.session_id)
    policy_input_query = resolved_query
    resolved_query, policy_transform = policies.rewrite_query(
        resolved_query,
        policy_assignment,
    )
    policy_plan = policies.plan_for_query(resolved_query, policy_assignment)
    effective_plan_output = llm_plan_output or (
        json.dumps(policy_plan, ensure_ascii=False) if policy_plan else None
    )

    plan = build_plan(resolved_query, llm_output=effective_plan_output)
    execution = execute_plan(
        resolved_query,
        plan,
        policy_retriever=policies.retriever_options(policy_assignment),
    )
    success = all(item["observation"].get("status") == "success" for item in execution["observations"])
    evidence_items = _extract_evidence_items(execution["observations"])
    citations = citations_from_evidence(evidence_items)
    execution_status = aggregate_execution_status(execution["observations"])
    draft_answer = generate_final_answer(plan, execution["observations"])
    answer, verification_result = DeterministicVerifier().verify_and_repair(
        plan=plan,
        observations=execution["observations"],
        answer=draft_answer,
        evidence_items=evidence_items,
        citations=citations,
        execution_status=execution_status,
        answer_composer=lambda: generate_final_answer(plan, execution["observations"]),
    )
    verification = verification_result.to_dict()
    trajectory = build_trajectory(
        resolved_query,
        plan,
        execution["observations"],
        answer,
        execution_status=execution_status,
        verification=verification,
    )

    result = {
        "query": query,
        "intent": plan["intent"],
        "selected_tool": plan["tool"],
        "arguments": plan["arguments"],
        "answer": answer,
        "used_tools": execution["used_tools"],
        "tool_call_count": len(execution["used_tools"]),
        "evidence": _extract_evidence_from_observations(execution["observations"]),
        "evidence_items": evidence_items,
        "citations": citations,
        "evidence_count": len(evidence_items),
        "execution_status": execution_status,
        "verification": verification,
        "confidence": _estimate_plan_confidence(plan, success),
        "success": success,
        "tool_schema_version": "prompt_v1",
        "planner_source": (
            planner_metadata.get("effective_provider") if planner_metadata
            else "llm_router" if llm_plan_output
            else "policy_engine" if policy_plan
            else "deterministic_planner"
        ),
        "provider": planner_metadata or {
            "provider_schema_version": "provider-v1",
            "requested_provider": "offline",
            "effective_provider": "offline",
            "status": "success",
            "model": "deterministic-planner-v1",
            "latency_ms": 0.0,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "fallback_used": False,
            "error_type": None,
            "execution_allowed": True,
        },
        "plan": plan["steps"],
        "trajectory": trajectory,
        "session_id": context.session_id,
        "trace_id": trace_id,
        "parent_trace_id": parent_trace_id,
        "resolved_query": resolved_query,
        "policy_input_query": policy_input_query,
        "policy_transform": policy_transform,
        "inherited_context": inherited_entities,
        "policy_version": policy_assignment.policy_id,
        "policy_assignment": policy_assignment.to_dict(),
        "trace_schema_version": "trace-v1",
        "replayable": True,
    }
    context = context_resolver.update(
        context,
        original_query=query,
        resolved_query=resolved_query,
        plan=plan,
        observations=execution["observations"],
        trace_id=trace_id,
        execution_status=execution_status,
    )
    context = sessions.save(context)
    result["context"] = context.to_dict()

    total_latency_ms = (time.perf_counter() - started_clock) * 1000
    trace = TraceRecorder().build(
        trace_id=trace_id,
        session_id=context.session_id,
        parent_trace_id=parent_trace_id,
        original_query=query,
        resolved_query=resolved_query,
        inherited_entities=inherited_entities,
        plan=plan,
        observations=execution["observations"],
        result=result,
        started_at=started_at,
        total_latency_ms=total_latency_ms,
    )
    result["trace"] = trace
    result["trace_persistence"] = traces.save(trace, persist=persist_trajectory)
    result["policy_monitor_event"] = policies.observe(
        policy_assignment,
        success=execution_status == "success" and verification.get("passed", False),
        latency_ms=total_latency_ms,
    )
    if persist_trajectory:
        result["memory"] = TrajectoryMemory().append(result)
    return result


def replay_trace(
    trace_id: str,
    *,
    trace_repository: TraceRepository | None = None,
) -> dict | None:
    """Reconstruct and execute one trace input without reusing prior session state."""
    traces = trace_repository or DEFAULT_TRACE_REPOSITORY
    return ReplayReader(traces).replay(trace_id, run_agent)


def execute_plan(
    query: str,
    plan: dict,
    *,
    policy_retriever: dict | None = None,
) -> dict:
    """Execute a planned sequence of tool calls."""
    observations = []
    used_tools = []
    package_candidates: list[str] = []

    for step in plan["steps"]:
        tool_name = step["tool"]
        tool_class = TOOL_REGISTRY[tool_name]
        if tool_name == "rag_retrieval" and policy_retriever:
            tool = tool_class(
                mode=policy_retriever["mode"],
                hybrid_weights={
                    "rrf_weight": policy_retriever["rrf_weight"],
                    "reranker_weight": policy_retriever["reranker_weight"],
                },
            )
        else:
            tool = tool_class()

        if tool_name in {"dependency_analysis", "version_compare"} and step["arguments"].get("from_previous_packages"):
            packages = package_candidates or [plan["arguments"].get("package")]
            packages = [package for package in packages if package]
            if not packages:
                observation = tool.run(query)
                observations.append({"tool": tool_name, "observation": observation, "step": step})
                used_tools.append(tool_name)
            else:
                for package in packages:
                    tool_query = (
                        f"{package} dependencies"
                        if tool_name == "dependency_analysis"
                        else f"compare {package} version changes"
                    )
                    observation = tool.run(tool_query)
                    observations.append({"tool": tool_name, "observation": observation, "step": step})
                    used_tools.append(tool_name)
            continue

        tool_query = None
        if tool_name in {"dependency_analysis", "version_compare"}:
            package = step["arguments"].get("package") or plan["arguments"].get("package")
            if package:
                tool_query = (
                    f"{package} dependencies"
                    if tool_name == "dependency_analysis"
                    else f"compare {package} version changes"
                )
        elif tool_name == "package_search":
            package = step["arguments"].get("package") or plan["arguments"].get("package")
            release = step["arguments"].get("release") or plan["arguments"].get("release")
            if package:
                tool_query = f"query {package} package info"
            elif release:
                tool_query = f"release {release} package list"
        if tool_query is None:
            tool_query = step["arguments"].get("query")
        if tool_query is None:
            tool_query = query
        observation = tool.run(tool_query)
        observations.append({"tool": tool_name, "observation": observation, "step": step})
        used_tools.append(tool_name)

        if tool_name == "package_search":
            package_candidates = _extract_packages_from_package_observation(observation)

    return {
        "used_tools": used_tools,
        "observations": observations
    }


def generate_final_answer(plan: dict, observations: list[dict]) -> str:
    """Generate an answer for single-tool or hybrid plans."""
    if plan["tool"] != "hybrid_plan":
        return generate_answer(plan, observations[0]["observation"])

    package_summaries = []
    dependency_summaries = []
    document_summaries = []
    version_summaries = []
    missing_summaries = []

    for item in observations:
        tool = item["tool"]
        observation = item["observation"]
        if observation.get("status") != "success":
            message = observation.get("message")
            if message:
                missing_summaries.append(message)
            continue
        if tool == "rag_retrieval":
            results = observation.get("results", [])
            if results:
                top = results[0]
                snippet = " ".join(top["content"].split())
                document_summaries.append(f"[{top['title']}] {snippet}")
        elif tool == "package_search":
            if observation.get("result_type") == "release_packages":
                package_summaries.extend(
                    f"{package['package']} {package['version']}"
                    for package in observation.get("result", [])
                )
            elif observation.get("result"):
                package = observation["result"]
                package_summaries.append(f"{package['package']} {package['version']}")
        elif tool == "dependency_analysis":
            if observation.get("result_type") == "reverse_dependency":
                dependents = ", ".join(observation.get("dependents", []))
                dependency_summaries.append(
                    f"{observation.get('component')} is required by: {dependents}"
                )
                continue
            dependencies = ", ".join(observation.get("dependencies", []))
            dependency_summaries.append(f"{observation.get('package')} depends on: {dependencies}")
        elif tool == "version_compare":
            changes = "; ".join(observation.get("changes", []))
            version_summaries.append(
                f"{observation.get('package')} changed from "
                f"{observation.get('old_version')} to {observation.get('new_version')}: {changes}"
            )

    parts = []
    if package_summaries:
        release = plan["arguments"].get("release")
        prefix = f"Release {release} contains" if release else "Target packages"
        parts.append(f"{prefix}: {', '.join(package_summaries)}.")
    if dependency_summaries:
        parts.append("Dependency analysis: " + "; ".join(dependency_summaries) + ".")
    if version_summaries:
        parts.append("Version changes: " + "; ".join(version_summaries) + ".")
    if missing_summaries:
        parts.append("Missing records: " + " ".join(missing_summaries))
    if document_summaries:
        parts.append("Document evidence: " + " ".join(document_summaries))
    return " ".join(parts) if parts else "No successful tool observations were available for the hybrid plan."


def generate_answer(route: dict, observation: dict) -> str:
    """Generate a concise deterministic answer from tool observation."""
    if observation.get("status") != "success":
        return observation.get("message", "No answer found in the simulated dataset.")

    tool = route["tool"]
    if tool == "component_mapping":
        return _answer_component_mapping(observation)
    if tool == "rag_retrieval":
        return _answer_rag_retrieval(observation)
    if tool == "package_search":
        return _answer_package_search(observation)
    if tool == "dependency_analysis":
        return _answer_dependency_analysis(observation)
    if tool == "version_compare":
        return _answer_version_compare(observation)
    return "The selected tool returned an unsupported observation type."


def build_trajectory(
    query: str,
    route: dict,
    observations: list[dict] | dict,
    answer: str,
    execution_status: str | None = None,
    verification: dict | None = None,
) -> list[dict]:
    """Build a ReAct-like execution trace for later evaluation."""
    observation_items = observations if isinstance(observations, list) else [{"tool": route["tool"], "observation": observations}]
    trajectory = [
        {
            "step": 1,
            "stage": "planning",
            "thought": route["reason"],
            "intent": route["intent"],
            "selected_tool": route["tool"],
            "arguments": route["arguments"],
            "tool_schema_version": "prompt_v1",
            "planner_source": "llm_router" if route.get("planner_fallback") is None else route["planner_fallback"],
            "plan": route.get("steps", [])
        }
    ]
    for index, item in enumerate(observation_items, start=2):
        trajectory.append({
            "step": index,
            "stage": "tool_execution",
            "tool": item["tool"],
            "observation": item["observation"],
            "reason": item.get("step", {}).get("reason")
        })
    trajectory.append({
        "step": len(trajectory) + 1,
        "stage": "answer_generation",
        "answer": answer,
        "execution_status": execution_status,
        "verification": verification,
    })
    return trajectory


def _answer_package_search(observation: dict) -> str:
    if observation.get("result_type") == "release_packages":
        release = observation["release"]
        packages = observation.get("result", [])
        if not packages:
            return f"No packages were found for release {release}."
        names = ", ".join(
            f"{item['package']} {item['version']}" for item in packages
        )
        return f"Release {release} contains these simulated packages: {names}."

    package = observation["result"]
    files = ", ".join(package.get("files", []))
    return (
        f"{package['package']} version {package['version']} "
        f"(release {package['release']}, {package['architecture']}) includes files: {files}."
    )


def _answer_dependency_analysis(observation: dict) -> str:
    if observation.get("result_type") == "reverse_dependency":
        dependents = ", ".join(observation.get("dependents", []))
        return f"{observation['component']} is required by: {dependents}."

    dependencies = observation.get("dependencies", [])
    if not dependencies:
        return f"{observation['package']} has no recorded dependencies in the simulated dataset."
    return f"{observation['package']} depends on: {', '.join(dependencies)}."


def _answer_version_compare(observation: dict) -> str:
    changes = "; ".join(observation.get("changes", []))
    return (
        f"{observation['package']} changed from {observation['old_version']} "
        f"to {observation['new_version']}. Changes: {changes}."
    )


def _answer_component_mapping(observation: dict) -> str:
    owners = observation.get("owners", [])
    component = observation.get("component", "the component")
    if not owners:
        return observation.get("message") or f"No package owns component {component} in the simulated dataset."
    owner_names = ", ".join(
        f"{package['package']} {package['version']} (release {package['release']})"
        for package in owners
    )
    return f"{component} belongs to package: {owner_names}."


def _answer_rag_retrieval(observation: dict) -> str:
    results = observation.get("results", [])
    if not results:
        return observation.get("message") or "No relevant document evidence was found."

    lines = []
    for result in results:
        snippet = " ".join(result["content"].split())
        lines.append(f"[{result['title']}] {snippet}")
    return "Relevant document evidence: " + " ".join(lines)


def _extract_evidence(observation: dict) -> list[str]:
    evidence = observation.get("evidence")
    if isinstance(evidence, list):
        return evidence
    return [evidence] if evidence else []


def _extract_evidence_from_observations(observations: list[dict]) -> list[str]:
    evidence: list[str] = []
    for item in observations:
        evidence.extend(_extract_evidence(item["observation"]))
    return sorted(set(evidence))


def _extract_evidence_items(observations: list[dict]) -> list[dict]:
    """Merge Evidence from multiple Tool calls while preserving first-seen order."""
    evidence_items: list[dict] = []
    seen: set[str] = set()
    for item in observations:
        for evidence in item["observation"].get("evidence_items", []):
            evidence_id = evidence["evidence_id"]
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            evidence_items.append(evidence)
    return evidence_items


def _estimate_confidence(route: dict, observation: dict) -> str:
    if observation.get("status") != "success":
        return "low"
    return route.get("confidence", "medium")


def _estimate_plan_confidence(plan: dict, success: bool) -> str:
    if not success:
        return "low"
    return plan.get("confidence", "medium")


def _extract_packages_from_package_observation(observation: dict) -> list[str]:
    if observation.get("status") != "success":
        return []
    if observation.get("result_type") == "release_packages":
        return [package["package"] for package in observation.get("result", [])]
    if observation.get("result"):
        return [observation["result"]["package"]]
    return []
