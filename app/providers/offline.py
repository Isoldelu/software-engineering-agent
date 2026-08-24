"""Zero-cost deterministic provider used by default and for fallback."""

from __future__ import annotations

from app.providers.models import ProviderRequest, ProviderResult


class OfflinePlanningProvider:
    name = "offline"

    def available(self) -> bool:
        return True

    def generate_plan(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status="success",
            plan_output=None,
            model="deterministic-planner-v1",
            latency_ms=0.0,
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )
