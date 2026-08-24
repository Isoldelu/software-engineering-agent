"""Shared execution wrapper for deterministic Agent Tools."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.evidence.normalizer import EvidenceNormalizer


def execute_tool_call(
    tool_name: str,
    query: str,
    handler: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Execute one Tool call and attach the compatible V2 observation."""
    started = perf_counter()
    observation = handler(query)
    latency_ms = (perf_counter() - started) * 1000
    return EvidenceNormalizer().normalize(
        tool_name,
        observation,
        latency_ms=latency_ms,
    )
