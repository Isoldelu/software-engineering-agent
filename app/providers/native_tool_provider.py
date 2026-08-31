"""Controlled DeepSeek native Tool Calling over the local deterministic Tools."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.llm_router import build_function_specs
from app.agent.verifier import aggregate_execution_status
from app.agent.workflow import TOOL_REGISTRY
from app.providers.settings import ProviderSettings

NATIVE_SYSTEM_PROMPT = """You are an AI4SE software-engineering Agent.
Use the supplied tools for every factual claim. Select the smallest sufficient set of tools.
For a compound request, call every tool needed to cover each explicit intent. When package_search
returns multiple release packages, call downstream dependency or version tools once per relevant
package. Never invent a tool or argument. After receiving tool results, answer concisely from those
results and explicitly acknowledge not-found evidence."""


@dataclass
class NativeToolResult:
    provider: str
    model: str
    status: str
    execution_status: str
    final_answer: str | None
    provider_rounds: int
    tool_call_count: int
    valid_tool_call_count: int
    invalid_tool_call_count: int
    used_tools: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    provider_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeepSeekNativeToolAgent:
    """Run a bounded model/tool loop while keeping local execution authoritative."""

    name = "deepseek_native_tools"

    def __init__(self, settings: ProviderSettings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    def available(self) -> bool:
        return self.settings.online_enabled and (
            self._client is not None or bool(os.getenv("DEEPSEEK_API_KEY"))
        )

    def run(self, query: str) -> NativeToolResult:
        started = time.perf_counter()
        if not self.settings.online_enabled:
            return self._error("online_disabled", "Online LLM access is not enabled.", started)
        if not os.getenv("DEEPSEEK_API_KEY") and self._client is None:
            return self._error("missing_api_key", "DEEPSEEK_API_KEY is not configured.", started)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": NATIVE_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        calls: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        provider_latency_ms = 0.0
        final_answer: str | None = None
        provider_rounds = 0
        error_type: str | None = None
        error_message: str | None = None

        try:
            client = self._client or self._build_client()
            for round_number in range(1, self.settings.native_max_rounds + 1):
                provider_started = time.perf_counter()
                response = client.chat.completions.create(
                    model=self.settings.deepseek_model,
                    messages=list(messages),
                    tools=build_function_specs(),
                    tool_choice="required" if round_number == 1 else "auto",
                    max_tokens=self.settings.max_output_tokens,
                    temperature=0,
                    stream=False,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                provider_latency_ms += _elapsed_ms(provider_started)
                provider_rounds += 1
                _merge_usage(usage, response)
                choice = response.choices[0]
                message = choice.message
                tool_calls = list(getattr(message, "tool_calls", None) or [])
                messages.append(_assistant_message(message, tool_calls))

                if not tool_calls:
                    content = getattr(message, "content", None)
                    final_answer = content.strip() if isinstance(content, str) else None
                    if getattr(choice, "finish_reason", None) == "length":
                        error_type = "output_truncated"
                        error_message = "The final model response reached the output limit."
                    break

                for index, tool_call in enumerate(tool_calls, start=1):
                    call_id = str(
                        getattr(tool_call, "id", None) or f"local-call-{round_number}-{index}"
                    )
                    name = str(getattr(tool_call.function, "name", ""))
                    arguments_text = str(getattr(tool_call.function, "arguments", ""))
                    validation_error, arguments = _validate_tool_call(name, arguments_text)
                    call_record: dict[str, Any] = {
                        "round": round_number,
                        "tool": name,
                        "arguments": arguments if arguments is not None else {},
                        "valid": validation_error is None,
                        "error_type": validation_error,
                    }

                    if len(calls) >= self.settings.native_max_tool_calls:
                        validation_error = "max_tool_calls_exceeded"
                        call_record["valid"] = False
                        call_record["error_type"] = validation_error
                    if validation_error:
                        call_record["observation_status"] = "blocked"
                        calls.append(call_record)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(
                                    {"status": "blocked", "error": validation_error},
                                    ensure_ascii=True,
                                ),
                            }
                        )
                        continue

                    assert arguments is not None
                    observation = TOOL_REGISTRY[name]().run(arguments["query"])
                    observations.append({"tool": name, "observation": observation})
                    call_record["observation_status"] = observation.get("status", "failed")
                    calls.append(call_record)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(
                                _compact_observation(observation),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    )
            else:
                error_type = "max_rounds_exceeded"
                error_message = "The model did not finish within the configured round limit."
        except ImportError:
            return self._error(
                "missing_dependency",
                "Install requirements-online.txt to use native Tool Calling.",
                started,
                usage=usage,
                provider_rounds=provider_rounds,
            )
        except TimeoutError as exc:
            error_type = "timeout"
            error_message = str(exc) or "Provider request timed out."
        except Exception as exc:  # noqa: BLE001 - normalize provider SDK errors
            error_type = type(exc).__name__
            error_message = _safe_message(str(exc))

        invalid_count = sum(not call["valid"] for call in calls)
        valid_count = len(calls) - invalid_count
        execution_status = aggregate_execution_status(observations)
        completed = final_answer is not None and error_type is None
        status = "success" if completed and valid_count > 0 and invalid_count == 0 else "error"
        return NativeToolResult(
            provider=self.name,
            model=self.settings.deepseek_model,
            status=status,
            execution_status=execution_status,
            final_answer=final_answer,
            provider_rounds=provider_rounds,
            tool_call_count=len(calls),
            valid_tool_call_count=valid_count,
            invalid_tool_call_count=invalid_count,
            used_tools=[item["tool"] for item in observations],
            tool_calls=calls,
            usage=usage,
            provider_latency_ms=round(provider_latency_ms, 3),
            total_latency_ms=_elapsed_ms(started),
            error_type=error_type,
            error_message=(error_message or "")[:300] or None,
        )

    def _build_client(self) -> Any:
        from openai import OpenAI

        return OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=self.settings.deepseek_base_url,
            timeout=self.settings.timeout_seconds,
            max_retries=0,
        )

    def _error(
        self,
        error_type: str,
        message: str,
        started: float,
        *,
        usage: dict[str, int] | None = None,
        provider_rounds: int = 0,
    ) -> NativeToolResult:
        return NativeToolResult(
            provider=self.name,
            model=self.settings.deepseek_model,
            status="error",
            execution_status="failed",
            final_answer=None,
            provider_rounds=provider_rounds,
            tool_call_count=0,
            valid_tool_call_count=0,
            invalid_tool_call_count=0,
            usage=usage or {},
            total_latency_ms=_elapsed_ms(started),
            error_type=error_type,
            error_message=_safe_message(message)[:300],
        )


def _validate_tool_call(name: str, arguments_text: str) -> tuple[str | None, dict[str, Any] | None]:
    if name not in TOOL_REGISTRY:
        return "unknown_tool", None
    try:
        arguments = json.loads(arguments_text)
    except (json.JSONDecodeError, TypeError):
        return "arguments_invalid_json", None
    if not isinstance(arguments, dict):
        return "arguments_must_be_object", None
    if set(arguments) != {"query"}:
        return "arguments_schema_mismatch", arguments
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        return "query_must_be_non_empty_string", arguments
    if len(query) > 1000:
        return "query_too_long", arguments
    return None, {"query": query.strip()}


def _assistant_message(message: Any, tool_calls: list[Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(message, "content", None),
    }
    if tool_calls:
        payload["tool_calls"] = [
            {
                "id": str(getattr(call, "id", "")),
                "type": "function",
                "function": {
                    "name": str(getattr(call.function, "name", "")),
                    "arguments": str(getattr(call.function, "arguments", "")),
                },
            }
            for call in tool_calls
        ]
    return payload


def _compact_observation(observation: dict[str, Any]) -> dict[str, Any]:
    excluded = {"evidence_items", "tool_call", "latency_ms"}
    return {key: value for key, value in observation.items() if key not in excluded}


def _merge_usage(target: dict[str, int], response: Any) -> None:
    usage = getattr(response, "usage", None)
    if not usage:
        return
    target["input_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
    target["output_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0)
    target["total_tokens"] += total or (
        int(getattr(usage, "prompt_tokens", 0) or 0)
        + int(getattr(usage, "completion_tokens", 0) or 0)
    )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _safe_message(message: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return message.replace(api_key, "[redacted]") if api_key else message
