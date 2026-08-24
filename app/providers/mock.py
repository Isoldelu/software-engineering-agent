"""Scripted provider used only for deterministic online-path evaluation."""

from __future__ import annotations

from collections.abc import Callable

from app.providers.models import ProviderRequest, ProviderResult


class MockPlanningProvider:
    name = "mock_online"

    def __init__(self, responder: Callable[[ProviderRequest], ProviderResult]) -> None:
        self.responder = responder
        self.call_count = 0

    def available(self) -> bool:
        return True

    def generate_plan(self, request: ProviderRequest) -> ProviderResult:
        self.call_count += 1
        return self.responder(request)
