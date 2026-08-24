"""LLM Router adapter.

This module accepts an LLM-style JSON plan, validates it against local tool
schemas, and normalizes it into the same plan format used by the deterministic
planner. It lets the demo show how a future LLM Router or function-calling
workflow can plug into the existing Agent executor.
"""

from __future__ import annotations

import json
from json import JSONDecodeError

from app.agent.prompt import TOOL_SCHEMAS, build_planner_prompt


VALID_TOOLS = {schema["name"] for schema in TOOL_SCHEMAS}
VALID_PLAN_TOOLS = VALID_TOOLS | {"hybrid_plan"}


def parse_llm_plan(query: str, llm_output: str) -> dict:
    """Parse and validate an LLM-produced JSON plan."""
    try:
        raw_plan = json.loads(_extract_json_payload(llm_output))
    except JSONDecodeError as exc:
        return _invalid_plan(query, f"invalid_json: {exc}")

    validation_error = validate_plan(raw_plan)
    if validation_error:
        return _invalid_plan(query, validation_error)

    return {
        "source": "llm_router",
        "valid": True,
        "plan": {
            "intent": raw_plan["intent"],
            "tool": raw_plan["tool"],
            "arguments": raw_plan.get("arguments", {}),
            "confidence": raw_plan.get("confidence", "medium"),
            "reason": raw_plan.get("reason", "LLM Router produced a validated tool plan."),
            "planner_prompt": build_planner_prompt(query),
            "steps": raw_plan["steps"]
        }
    }


def validate_plan(plan: dict) -> str | None:
    """Return None when valid, otherwise an error string."""
    if not isinstance(plan, dict):
        return "plan_must_be_object"
    if plan.get("tool") not in VALID_PLAN_TOOLS:
        return f"unknown_plan_tool: {plan.get('tool')}"
    if not isinstance(plan.get("intent"), str) or not plan["intent"]:
        return "missing_intent"
    if not isinstance(plan.get("steps"), list) or not plan["steps"]:
        return "missing_steps"

    for index, step in enumerate(plan["steps"], start=1):
        if not isinstance(step, dict):
            return f"step_{index}_must_be_object"
        if step.get("tool") not in VALID_TOOLS:
            return f"step_{index}_unknown_tool: {step.get('tool')}"
        if not isinstance(step.get("arguments", {}), dict):
            return f"step_{index}_arguments_must_be_object"
        if not isinstance(step.get("reason", ""), str):
            return f"step_{index}_reason_must_be_string"
    return None


def build_function_specs() -> list[dict]:
    """Export a function-calling friendly view of the local tool schemas."""
    specs = []
    for schema in TOOL_SCHEMAS:
        specs.append({
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        key: {
                            "type": "string",
                            "description": description
                        }
                        for key, description in schema["inputs"].items()
                    },
                    "required": list(schema["inputs"].keys())
                }
            }
        })
    return specs


def _extract_json_payload(llm_output: str) -> str:
    stripped = llm_output.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _invalid_plan(query: str, error: str) -> dict:
    return {
        "source": "llm_router",
        "valid": False,
        "error": error,
        "planner_prompt": build_planner_prompt(query)
    }
