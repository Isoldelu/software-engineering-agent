"""Structured, redacted security and control-plane audit events."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.observability.audit_sink import AuditSink
from app.storage.database import ControlPlaneStore


class AuditRepository:
    def __init__(self, store: ControlPlaneStore, *, sink: AuditSink | None = None) -> None:
        self.store = store
        self.sink = sink or AuditSink.from_env()

    def record(
        self,
        *,
        event_type: str,
        resource: str,
        action: str,
        outcome: str,
        actor_fingerprint: str | None = None,
        actor_role: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": f"audit_{uuid.uuid4().hex}",
            "event_type": event_type,
            "actor_fingerprint": actor_fingerprint,
            "actor_role": actor_role,
            "resource": resource,
            "action": action,
            "outcome": outcome,
            "details": details or {},
            "created_at": time.time(),
        }
        marker = self.store.placeholder
        try:
            with self.store.transaction(write=True) as cursor:
                cursor.execute(
                    f"INSERT INTO control_plane_audit "
                    f"(event_id, event_type, actor_fingerprint, actor_role, resource, "
                    f"action, outcome, details, created_at) VALUES "
                    f"({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, "
                    f"{marker}, {marker}, {marker})",
                    (
                        event["event_id"],
                        event_type,
                        actor_fingerprint,
                        actor_role,
                        resource,
                        action,
                        outcome,
                        json.dumps(event["details"], sort_keys=True),
                        event["created_at"],
                    ),
                )
        finally:
            self.sink.emit(event)
        return event

    def list(self, *, limit: int = 100, since: float | None = None) -> list[dict[str, Any]]:
        marker = self.store.placeholder
        bounded_limit = max(1, min(int(limit), 1000))
        query = (
            "SELECT event_id, event_type, actor_fingerprint, actor_role, resource, "
            "action, outcome, details, created_at FROM control_plane_audit"
        )
        params: tuple[Any, ...]
        if since is not None:
            query += f" WHERE created_at >= {marker}"
            params = (since, bounded_limit)
        else:
            params = (bounded_limit,)
        query += f" ORDER BY created_at DESC LIMIT {marker}"
        with self.store.transaction() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [
            {
                "event_id": str(row[0]),
                "event_type": str(row[1]),
                "actor_fingerprint": str(row[2]) if row[2] is not None else None,
                "actor_role": str(row[3]) if row[3] is not None else None,
                "resource": str(row[4]),
                "action": str(row[5]),
                "outcome": str(row[6]),
                "details": json.loads(row[7]),
                "created_at": float(row[8]),
            }
            for row in rows
        ]

    def prune(self, *, older_than: float, limit: int = 1000, dry_run: bool = False) -> int:
        marker = self.store.placeholder
        bounded_limit = max(1, min(int(limit), 10_000))
        with self.store.transaction(write=not dry_run) as cursor:
            cursor.execute(
                f"SELECT event_id FROM control_plane_audit WHERE created_at < {marker} "
                f"ORDER BY created_at, event_id LIMIT {marker}",
                (older_than, bounded_limit),
            )
            event_ids = [str(row[0]) for row in cursor.fetchall()]
            if dry_run:
                return len(event_ids)
            for event_id in event_ids:
                cursor.execute(
                    f"DELETE FROM control_plane_audit WHERE event_id = {marker}",
                    (event_id,),
                )
        return len(event_ids)
