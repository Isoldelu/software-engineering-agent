"""Environment-backed provider configuration with online opt-in."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float_setting(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class ProviderSettings:
    default_provider: str = "offline"
    online_enabled: bool = False
    openai_model: str = "gpt-5-mini"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = 20.0
    max_output_tokens: int = 800

    @classmethod
    def from_env(cls) -> ProviderSettings:
        default_provider = os.getenv("SOFTWARE_AGENT_LLM_PROVIDER", "offline").strip().lower()
        if default_provider not in {"offline", "openai", "deepseek"}:
            default_provider = "offline"
        return cls(
            default_provider=default_provider,
            online_enabled=_enabled(os.getenv("SOFTWARE_AGENT_ENABLE_ONLINE_LLM")),
            openai_model=os.getenv("SOFTWARE_AGENT_OPENAI_MODEL", "gpt-5-mini").strip(),
            deepseek_model=os.getenv(
                "SOFTWARE_AGENT_DEEPSEEK_MODEL", "deepseek-v4-flash"
            ).strip(),
            deepseek_base_url=os.getenv(
                "SOFTWARE_AGENT_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).strip().rstrip("/"),
            timeout_seconds=_float_setting("SOFTWARE_AGENT_LLM_TIMEOUT", 20.0, 1.0, 60.0),
            max_output_tokens=_int_setting(
                "SOFTWARE_AGENT_LLM_MAX_OUTPUT_TOKENS", 800, 128, 2000
            ),
        )

    def public_status(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["openai_api_key_configured"] = bool(os.getenv("OPENAI_API_KEY"))
        payload["deepseek_api_key_configured"] = bool(os.getenv("DEEPSEEK_API_KEY"))
        return payload
