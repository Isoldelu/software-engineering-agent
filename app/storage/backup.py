"""Checksum-protected logical backup and restore for control-plane records."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.storage.database import ControlPlaneStore

BACKUP_FORMAT = "control-plane-logical-v1"


class BackupIntegrityError(RuntimeError):
    """Raised when a backup manifest does not match its payload."""


class ControlPlaneBackupService:
    def __init__(self, store: ControlPlaneStore) -> None:
        self.store = store

    def create(
        self,
        path: Path,
        *,
        namespaces: list[str] | None = None,
    ) -> dict[str, Any]:
        selected = sorted(set(namespaces or self.store.namespaces()))
        records = [
            {
                "namespace": item.namespace,
                "record_id": item.record_id,
                "payload": item.payload,
                "source_version": item.version,
                "source_updated_at": item.updated_at,
            }
            for namespace in selected
            for item in self.store.list(namespace)
        ]
        payload = {"namespaces": selected, "records": records}
        checksum = _checksum(payload)
        manifest: dict[str, Any] = {
            "format": BACKUP_FORMAT,
            "created_at": datetime.now(UTC).isoformat(),
            "record_count": len(records),
            "checksum_sha256": checksum,
            "includes_api_key_registry": False,
            "includes_audit": False,
        }
        document: dict[str, Any] = {
            "manifest": manifest,
            **payload,
        }
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return {**manifest, "path": str(path), "credentials_exposed": False}

    def verify(self, path: Path) -> dict[str, Any]:
        document = _load(path)
        manifest = document.get("manifest", {})
        if manifest.get("format") != BACKUP_FORMAT:
            raise BackupIntegrityError("Unsupported control-plane backup format.")
        payload = {
            "namespaces": document.get("namespaces", []),
            "records": document.get("records", []),
        }
        actual = _checksum(payload)
        if manifest.get("checksum_sha256") != actual:
            raise BackupIntegrityError("Control-plane backup checksum mismatch.")
        if manifest.get("record_count") != len(payload["records"]):
            raise BackupIntegrityError("Control-plane backup record count mismatch.")
        return {
            **manifest,
            "path": str(path.resolve()),
            "verified": True,
            "credentials_exposed": False,
        }

    def restore(self, path: Path, *, clear_existing: bool = False) -> dict[str, Any]:
        verification = self.verify(path)
        document = _load(path)
        namespaces = [str(item) for item in document["namespaces"]]
        owner = f"restore-{uuid.uuid4().hex}"
        restored = 0
        with self.store.lease("control-plane-restore", owner, ttl_seconds=300):
            if clear_existing:
                for namespace in namespaces:
                    self.store.delete_namespace(namespace)
            for item in document["records"]:
                namespace = str(item["namespace"])
                record_id = str(item["record_id"])
                current = self.store.get(namespace, record_id)
                self.store.upsert(
                    namespace,
                    record_id,
                    dict(item["payload"]),
                    expected_version=current.version if current else 0,
                )
                restored += 1
        return {
            "format": verification["format"],
            "verified": True,
            "restored_records": restored,
            "namespaces": namespaces,
            "clear_existing": clear_existing,
            "restored_at": time.time(),
        }


def _checksum(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupIntegrityError("Control-plane backup cannot be read.") from exc
    if not isinstance(document, dict):
        raise BackupIntegrityError("Control-plane backup root must be an object.")
    return document
