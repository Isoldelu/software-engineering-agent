"""Validated provider selection and deterministic fallback gateway."""

from __future__ import annotations

from typing import Any

from app.agent.llm_router import parse_llm_plan
from app.agent.prompt import build_planner_prompt
from app.providers.base import PlanningProvider
from app.providers.models import PlannerDecision, ProviderRequest, ProviderResult
from app.providers.offline import OfflinePlanningProvider
from app.providers.openai_provider import OpenAIPlanningProvider
from app.providers.settings import ProviderSettings


class PlannerGateway:
    def __init__(
        self,
        settings: ProviderSettings | None = None,
        *,
        providers: dict[str, PlanningProvider] | None = None,
    ) -> None:
        self.settings = settings or ProviderSettings.from_env()
        self.providers = providers or {
            "offline": OfflinePlanningProvider(),
            "openai": OpenAIPlanningProvider(self.settings),
        }

    def plan(
        self,
        query: str,
        *,
        provider: str = "auto",
        allow_fallback: bool = True,
    ) -> PlannerDecision:
        requested = self.settings.default_provider if provider == "auto" else provider
        if requested not in self.providers:
            return self._fallback(
                requested,
                ProviderResult(
                    provider=requested,
                    status="error",
                    plan_output=None,
                    error_type="unknown_provider",
                    error_message=f"Unknown provider: {requested}",
                ),
                allow_fallback,
            )
        selected = self.providers[requested]
        if requested != "offline" and not selected.available():
            return self._fallback(
                requested,
                ProviderResult(
                    provider=requested,
                    status="error",
                    plan_output=None,
                    error_type="provider_unavailable",
                    error_message="Provider is disabled, missing credentials, or unavailable.",
                ),
                allow_fallback,
            )
        request = ProviderRequest(
            query=query,
            prompt=build_planner_prompt(query),
            timeout_seconds=self.settings.timeout_seconds,
            max_output_tokens=self.settings.max_output_tokens,
        )
        result = selected.generate_plan(request)
        if result.status != "success":
            return self._fallback(requested, result, allow_fallback)
        if result.plan_output is not None:
            parsed = parse_llm_plan(query, result.plan_output)
            if not parsed["valid"]:
                result.status = "error"
                result.error_type = "invalid_plan"
                result.error_message = parsed["error"]
                return self._fallback(requested, result, allow_fallback)
        return PlannerDecision(
            plan_output=result.plan_output,
            metadata=self._metadata(
                requested=requested,
                effective=result.provider,
                result=result,
                fallback_used=False,
            ),
        )

    def status(self) -> dict[str, Any]:
        return {
            "settings": self.settings.public_status(),
            "providers": {
                name: {"available": provider.available()}
                for name, provider in self.providers.items()
            },
            "secrets_exposed": False,
        }

    def _fallback(
        self,
        requested: str,
        failed: ProviderResult,
        allow_fallback: bool,
    ) -> PlannerDecision:
        if not allow_fallback:
            return PlannerDecision(
                plan_output=None,
                metadata=self._metadata(
                    requested=requested,
                    effective="none",
                    result=failed,
                    fallback_used=False,
                ) | {"execution_allowed": False},
            )
        offline = self.providers.get("offline", OfflinePlanningProvider())
        request = ProviderRequest("", "", 0.0, 0)
        fallback = offline.generate_plan(request)
        metadata = self._metadata(
            requested=requested,
            effective="offline",
            result=fallback,
            fallback_used=True,
        )
        metadata["fallback_reason"] = {
            "error_type": failed.error_type,
            "error_message": failed.error_message,
        }
        return PlannerDecision(plan_output=None, metadata=metadata)

    @staticmethod
    def _metadata(
        *,
        requested: str,
        effective: str,
        result: ProviderResult,
        fallback_used: bool,
    ) -> dict[str, Any]:
        return {
            "provider_schema_version": "provider-v1",
            "requested_provider": requested,
            "effective_provider": effective,
            "status": result.status,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "usage": result.usage,
            "fallback_used": fallback_used,
            "error_type": result.error_type,
            "execution_allowed": True,
        }


DEFAULT_PLANNER_GATEWAY = PlannerGateway()
