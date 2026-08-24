"""Provider protocol for structured Agent planning."""

from __future__ import annotations

from typing import Protocol

from app.providers.models import ProviderRequest, ProviderResult


class PlanningProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate_plan(self, request: ProviderRequest) -> ProviderResult: ...
