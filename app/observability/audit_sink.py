"""Independent append-only JSONL audit export with strict field filtering."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.observability.metrics import DEFAULT_METRICS

AUDIT_LOG_PATH_ENV = "SOFTWARE_AGENT_AUDIT_LOG_PATH"
FORBIDDEN_FIELDS = {"api_key", "secret", "secret_hash", "request_body", "query"}


class AuditSink:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    @classmethod
    def from_env(cls) -> AuditSink:
        configured = os.getenv(AUDIT_LOG_PATH_ENV, "").strip()
        return cls(Path(configured).resolve() if configured and configured != "-" else None)

    @property
    def enabled(self) -> bool:
        return self.path is not None or os.getenv(AUDIT_LOG_PATH_ENV, "").strip() == "-"

    def emit(self, event: dict[str, Any]) -> bool:
        if not self.enabled:
            return True
        try:
            _validate_fields(event)
            serialized = json.dumps(
                {"schema_version": "audit-event-v1", **event},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
            if self.path is None:
                print(serialized, end="")
                return True
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, serialized.encode("utf-8"))
            finally:
                os.close(descriptor)
            return True
        except Exception:  # noqa: BLE001 - audit sink must not break the API path
            DEFAULT_METRICS.observe_audit_sink_failure()
            return False


def _validate_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_FIELDS:
                raise ValueError(f"Forbidden audit field: {key}")
            _validate_fields(child)
    elif isinstance(value, list):
        for child in value:
            _validate_fields(child)
