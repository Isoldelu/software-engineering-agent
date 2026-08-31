"""Optional DeepSeek JSON-planning provider with local plan validation."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.providers.models import ProviderRequest, ProviderResult
from app.providers.settings import ProviderSettings


class DeepSeekPlanningProvider:
    name = "deepseek"

    def __init__(self, settings: ProviderSettings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    def available(self) -> bool:
        return self.settings.online_enabled and bool(os.getenv("DEEPSEEK_API_KEY"))

    def generate_plan(self, request: ProviderRequest) -> ProviderResult:
        started = time.perf_counter()
        if not self.settings.online_enabled:
            return self._error("online_disabled", "Online LLM access is not enabled.", started)
        if not os.getenv("DEEPSEEK_API_KEY") and self._client is None:
            return self._error(
                "missing_api_key", "DEEPSEEK_API_KEY is not configured.", started
            )
        try:
            client = self._client or self._build_client(request.timeout_seconds)
            response = client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a software-engineering Agent planner. "
                            "Return one valid JSON object only; do not use markdown."
                        ),
                    },
                    {"role": "user", "content": request.prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=request.max_output_tokens,
                temperature=0,
                stream=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
            output_text = response.choices[0].message.content or ""
            json.loads(output_text)
            return ProviderResult(
                provider=self.name,
                status="success",
                plan_output=output_text,
                model=getattr(response, "model", None) or self.settings.deepseek_model,
                latency_ms=_elapsed_ms(started),
                usage=_usage(response),
            )
        except ImportError:
            return self._error(
                "missing_dependency",
                "Install requirements-online.txt to use the DeepSeek provider.",
                started,
            )
        except TimeoutError as exc:
            return self._error("timeout", str(exc) or "Provider request timed out.", started)
        except (json.JSONDecodeError, ValueError) as exc:
            return self._error("invalid_response", str(exc), started)
        except Exception as exc:  # noqa: BLE001 - normalize provider SDK errors
            return self._error(type(exc).__name__, _safe_message(str(exc)), started)

    def _build_client(self, timeout_seconds: float) -> Any:
        from openai import OpenAI

        return OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=self.settings.deepseek_base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def _error(self, error_type: str, message: str, started: float) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status="error",
            plan_output=None,
            model=self.settings.deepseek_model,
            latency_ms=_elapsed_ms(started),
            error_type=error_type,
            error_message=message[:300],
        )


def _usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens or input_tokens + output_tokens,
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _safe_message(message: str) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return message.replace(api_key, "[redacted]") if api_key else message
