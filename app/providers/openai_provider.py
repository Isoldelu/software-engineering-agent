"""Optional OpenAI Responses API provider for structured plans."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.agent.llm_router import VALID_TOOLS
from app.providers.models import ProviderRequest, ProviderResult
from app.providers.settings import ProviderSettings


PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string"},
        "tool": {"type": "string", "enum": sorted(VALID_TOOLS | {"hybrid_plan"})},
        "arguments": {"type": "object", "additionalProperties": True},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reason": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tool": {"type": "string", "enum": sorted(VALID_TOOLS)},
                    "arguments": {"type": "object", "additionalProperties": True},
                    "reason": {"type": "string"},
                },
                "required": ["tool", "arguments", "reason"],
            },
        },
    },
    "required": ["intent", "tool", "arguments", "confidence", "reason", "steps"],
}


class OpenAIPlanningProvider:
    name = "openai"

    def __init__(self, settings: ProviderSettings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    def available(self) -> bool:
        return self.settings.online_enabled and bool(os.getenv("OPENAI_API_KEY"))

    def generate_plan(self, request: ProviderRequest) -> ProviderResult:
        started = time.perf_counter()
        if not self.settings.online_enabled:
            return self._error("online_disabled", "Online LLM access is not enabled.", started)
        if not os.getenv("OPENAI_API_KEY") and self._client is None:
            return self._error("missing_api_key", "OPENAI_API_KEY is not configured.", started)
        try:
            client = self._client or self._build_client(request.timeout_seconds)
            response = client.responses.create(
                model=self.settings.openai_model,
                input=request.prompt,
                max_output_tokens=request.max_output_tokens,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "software_agent_plan",
                        "schema": PLAN_SCHEMA,
                        "strict": True,
                    }
                },
            )
            output_text = response.output_text
            json.loads(output_text)
            return ProviderResult(
                provider=self.name,
                status="success",
                plan_output=output_text,
                model=self.settings.openai_model,
                latency_ms=_elapsed_ms(started),
                usage=_usage(response),
            )
        except ImportError:
            return self._error(
                "missing_dependency",
                "Install requirements-online.txt to use the OpenAI provider.",
                started,
            )
        except TimeoutError as exc:
            return self._error("timeout", str(exc) or "Provider request timed out.", started)
        except (json.JSONDecodeError, ValueError) as exc:
            return self._error("invalid_response", str(exc), started)
        except Exception as exc:  # Provider SDK errors are normalized at this boundary.
            return self._error(type(exc).__name__, _safe_message(str(exc)), started)

    def _build_client(self, timeout_seconds: float) -> Any:
        from openai import OpenAI

        return OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=timeout_seconds, max_retries=0)

    def _error(self, error_type: str, message: str, started: float) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status="error",
            plan_output=None,
            model=self.settings.openai_model,
            latency_ms=_elapsed_ms(started),
            error_type=error_type,
            error_message=message[:300],
        )


def _usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _safe_message(message: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    return message.replace(api_key, "[redacted]") if api_key else message
