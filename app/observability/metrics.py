"""Dependency-free Prometheus text exposition for bounded service metrics."""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from prometheus_client import (
        REGISTRY,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
        multiprocess,
    )
except ImportError:  # pragma: no cover - exercised by the dependency-free local runtime
    CollectorRegistry = Counter = Histogram = REGISTRY = None
    generate_latest = multiprocess = None

HISTOGRAM_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


@dataclass
class HistogramState:
    bucket_counts: list[int] = field(
        default_factory=lambda: [0 for _ in HISTOGRAM_BUCKETS]
    )
    total: float = 0.0
    count: int = 0

    def observe(self, value: float) -> None:
        self.total += value
        self.count += 1
        for index, bucket in enumerate(HISTOGRAM_BUCKETS):
            if value <= bucket:
                self.bucket_counts[index] += 1


class MetricsRegistry:
    def __init__(self, *, prometheus_registry: Any | None = None) -> None:
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._durations: dict[tuple[str, str], HistogramState] = defaultdict(HistogramState)
        self._auth_denials: dict[str, int] = defaultdict(int)
        self._audit_sink_failures = 0
        self._retention_deleted: dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
        self._prometheus_registry = None
        self._prometheus_multiprocess = False
        if Counter is not None:
            registry = prometheus_registry or CollectorRegistry()
            self._prometheus_registry = registry
            self._prometheus_multiprocess = registry is REGISTRY and bool(
                os.getenv("PROMETHEUS_MULTIPROC_DIR")
            )
            self._prom_requests = Counter(
                "software_agent_http_requests_total",
                "HTTP requests by route and status.",
                ("method", "route", "status"),
                registry=registry,
            )
            self._prom_durations = Histogram(
                "software_agent_http_request_duration_seconds",
                "HTTP request latency.",
                ("method", "route"),
                buckets=HISTOGRAM_BUCKETS,
                registry=registry,
            )
            self._prom_auth_denials = Counter(
                "software_agent_auth_denials_total",
                "Authentication and authorization denials.",
                ("reason",),
                registry=registry,
            )
            self._prom_audit_failures = Counter(
                "software_agent_audit_sink_failures_total",
                "Independent audit export failures.",
                registry=registry,
            )
            self._prom_retention = Counter(
                "software_agent_retention_deleted_total",
                "Records deleted by retention.",
                ("namespace",),
                registry=registry,
            )

    def observe_request(
        self, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        bounded_route = route if route.startswith("/") else "unknown"
        with self._lock:
            self._requests[(method.upper(), bounded_route, str(status_code))] += 1
            self._durations[(method.upper(), bounded_route)].observe(duration_seconds)
            if self._prometheus_registry is not None:
                self._prom_requests.labels(
                    method=method.upper(), route=bounded_route, status=str(status_code)
                ).inc()
                self._prom_durations.labels(
                    method=method.upper(), route=bounded_route
                ).observe(duration_seconds)

    def observe_auth_denial(self, reason: str) -> None:
        with self._lock:
            self._auth_denials[reason] += 1
            if self._prometheus_registry is not None:
                self._prom_auth_denials.labels(reason=reason).inc()

    def observe_audit_sink_failure(self) -> None:
        with self._lock:
            self._audit_sink_failures += 1
            if self._prometheus_registry is not None:
                self._prom_audit_failures.inc()

    def observe_retention(self, namespace: str, deleted: int) -> None:
        if deleted <= 0:
            return
        with self._lock:
            self._retention_deleted[namespace] += deleted
            if self._prometheus_registry is not None:
                self._prom_retention.labels(namespace=namespace).inc(deleted)

    def render(self, *, storage: dict[str, Any] | None = None) -> str:
        if self._prometheus_registry is not None:
            if self._prometheus_multiprocess:
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
            else:
                registry = self._prometheus_registry
            lines = generate_latest(registry).decode("utf-8").rstrip().splitlines()
            return _append_storage_metrics(lines, storage)
        with self._lock:
            lines = [
                "# HELP software_agent_http_requests_total HTTP requests by route and status.",
                "# TYPE software_agent_http_requests_total counter",
            ]
            for (method, route, status), count in sorted(self._requests.items()):
                labels = _labels(method=method, route=route, status=status)
                lines.append(f"software_agent_http_requests_total{{{labels}}} {count}")
            lines.extend(
                [
                    "# HELP software_agent_http_request_duration_seconds HTTP request latency.",
                    "# TYPE software_agent_http_request_duration_seconds histogram",
                ]
            )
            for (method, route), state in sorted(self._durations.items()):
                base = _labels(method=method, route=route)
                for bucket, count in zip(
                    HISTOGRAM_BUCKETS, state.bucket_counts, strict=True
                ):
                    lines.append(
                        "software_agent_http_request_duration_seconds_bucket"
                        f'{{{base},le="{bucket:g}"}} {count}'
                    )
                lines.append(
                    "software_agent_http_request_duration_seconds_bucket"
                    f'{{{base},le="+Inf"}} {state.count}'
                )
                lines.append(
                    "software_agent_http_request_duration_seconds_sum"
                    f"{{{base}}} {state.total:.9f}"
                )
                lines.append(
                    "software_agent_http_request_duration_seconds_count"
                    f"{{{base}}} {state.count}"
                )
            lines.extend(
                [
                    "# HELP software_agent_auth_denials_total Authentication and authorization denials.",
                    "# TYPE software_agent_auth_denials_total counter",
                ]
            )
            for reason, count in sorted(self._auth_denials.items()):
                lines.append(
                    f"software_agent_auth_denials_total{{reason={_quote(reason)}}} {count}"
                )
            lines.extend(
                [
                    "# HELP software_agent_audit_sink_failures_total Independent audit export failures.",
                    "# TYPE software_agent_audit_sink_failures_total counter",
                    f"software_agent_audit_sink_failures_total {self._audit_sink_failures}",
                    "# HELP software_agent_retention_deleted_total Records deleted by retention.",
                    "# TYPE software_agent_retention_deleted_total counter",
                ]
            )
            for namespace, count in sorted(self._retention_deleted.items()):
                lines.append(
                    "software_agent_retention_deleted_total"
                    f"{{namespace={_quote(namespace)}}} {count}"
                )
        return _append_storage_metrics(lines, storage)


def _labels(**values: str) -> str:
    return ",".join(f"{key}={_quote(value)}" for key, value in values.items())


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    return f'"{escaped}"'


def _append_storage_metrics(
    lines: list[str], storage: dict[str, Any] | None
) -> str:
    if storage is not None:
        lines.extend(
            [
                "# HELP software_agent_storage_healthy Control-plane storage health.",
                "# TYPE software_agent_storage_healthy gauge",
                f"software_agent_storage_healthy {1 if storage.get('healthy') else 0}",
            ]
        )
        pool = storage.get("pool") or {}
        for name in ("pool_size", "pool_available", "requests_waiting"):
            value = pool.get(name)
            if isinstance(value, (int, float)):
                lines.append(f"software_agent_db_{name} {value}")
    return "\n".join(lines) + "\n"


def _prepare_multiprocess_directory() -> None:
    configured = os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if configured:
        Path(configured).mkdir(parents=True, exist_ok=True)


_prepare_multiprocess_directory()
DEFAULT_METRICS = MetricsRegistry(prometheus_registry=REGISTRY)
