"""Database-backed API Key rotation and revocation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.storage.database import ControlPlaneStore

VALID_ROLES = {"reader", "operator", "admin"}
PEPPER_ENV = "SOFTWARE_AGENT_API_KEY_PEPPER"


@dataclass(frozen=True)
class RegisteredKey:
    key_id: str
    role: str
    status: str
    created_at: float
    expires_at: float | None
    grace_until: float | None
    rotated_from: str | None
    metadata: dict[str, Any]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "grace_until": self.grace_until,
            "rotated_from": self.rotated_from,
            "metadata": self.metadata,
            "secret_exposed": False,
        }


class KeyRegistry:
    def __init__(self, store: ControlPlaneStore, *, pepper: str | None = None) -> None:
        self.store = store
        self.pepper = pepper if pepper is not None else os.getenv(PEPPER_ENV, "")

    def rotate(
        self,
        role: str,
        *,
        actor: str,
        grace_seconds: float = 0,
        ttl_seconds: float | None = None,
    ) -> dict[str, Any]:
        if role not in VALID_ROLES:
            raise ValueError(f"Unsupported API Key role: {role}")
        if grace_seconds < 0 or (ttl_seconds is not None and ttl_seconds <= 0):
            raise ValueError("Grace must be non-negative and TTL must be positive.")
        owner = f"rotation-{uuid.uuid4().hex}"
        with self.store.lease(
            f"api-key-rotation:{role}", owner, ttl_seconds=10, wait_timeout=3
        ):
            now = time.time()
            existing = self.list(role=role, include_expired=True)
            active_ids = [item.key_id for item in existing if item.status == "active"]
            raw_key = secrets.token_urlsafe(32)
            key_id = f"key_{uuid.uuid4().hex[:16]}"
            expires_at = now + ttl_seconds if ttl_seconds is not None else None
            marker = self.store.placeholder
            with self.store.transaction(write=True) as cursor:
                next_status = "grace" if grace_seconds > 0 else "revoked"
                grace_until = now + grace_seconds if grace_seconds > 0 else None
                for old_key_id in active_ids:
                    cursor.execute(
                        f"UPDATE api_key_registry SET status = {marker}, "
                        f"grace_until = {marker} WHERE key_id = {marker}",
                        (next_status, grace_until, old_key_id),
                    )
                cursor.execute(
                    f"INSERT INTO api_key_registry "
                    f"(key_id, role, secret_hash, status, created_at, expires_at, "
                    f"grace_until, rotated_from, metadata) VALUES "
                    f"({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, "
                    f"{marker}, {marker}, {marker})",
                    (
                        key_id,
                        role,
                        self.hash_secret(raw_key),
                        "active",
                        now,
                        expires_at,
                        None,
                        active_ids[-1] if active_ids else None,
                        json.dumps({"created_by": actor}, sort_keys=True),
                    ),
                )
        return {
            "key_id": key_id,
            "role": role,
            "api_key": raw_key,
            "created_at": now,
            "expires_at": expires_at,
            "grace_seconds": grace_seconds,
            "returned_once": True,
        }

    def authenticate(self, provided_key: str) -> RegisteredKey | None:
        secret_hash = self.hash_secret(provided_key)
        marker = self.store.placeholder
        now = time.time()
        with self.store.transaction() as cursor:
            cursor.execute(
                f"SELECT key_id, role, status, created_at, expires_at, grace_until, "
                f"rotated_from, metadata FROM api_key_registry WHERE secret_hash = {marker}",
                (secret_hash,),
            )
            row = cursor.fetchone()
        item = _registered_key(row) if row else None
        if not item or not self._usable(item, now):
            return None
        return item

    def managed_roles(self) -> set[str]:
        with self.store.transaction() as cursor:
            cursor.execute("SELECT DISTINCT role FROM api_key_registry")
            return {str(row[0]) for row in cursor.fetchall()}

    def list(
        self,
        *,
        role: str | None = None,
        include_expired: bool = False,
    ) -> list[RegisteredKey]:
        marker = self.store.placeholder
        query = (
            "SELECT key_id, role, status, created_at, expires_at, grace_until, "
            "rotated_from, metadata FROM api_key_registry"
        )
        params: tuple[Any, ...] = ()
        if role:
            query += f" WHERE role = {marker}"
            params = (role,)
        query += " ORDER BY created_at, key_id"
        with self.store.transaction() as cursor:
            cursor.execute(query, params)
            items = [_registered_key(row) for row in cursor.fetchall()]
        if include_expired:
            return items
        now = time.time()
        return [item for item in items if self._usable(item, now)]

    def revoke(self, key_id: str, *, actor: str) -> RegisteredKey:
        existing = self.get(key_id)
        if not existing:
            raise KeyError(f"API Key not found: {key_id}")
        if existing.role == "admin" and existing.status != "revoked":
            remaining = [
                item for item in self.list(role="admin") if item.key_id != key_id
            ]
            if not remaining:
                raise ValueError("Cannot revoke the final usable database-managed admin key.")
        marker = self.store.placeholder
        metadata = dict(existing.metadata)
        metadata.update({"revoked_by": actor, "revoked_at": time.time()})
        with self.store.transaction(write=True) as cursor:
            cursor.execute(
                f"UPDATE api_key_registry SET status = {marker}, grace_until = {marker}, "
                f"metadata = {marker} WHERE key_id = {marker}",
                ("revoked", None, json.dumps(metadata, sort_keys=True), key_id),
            )
        revoked = self.get(key_id)
        if not revoked:
            raise RuntimeError("Revoked API Key disappeared from the registry.")
        return revoked

    def get(self, key_id: str) -> RegisteredKey | None:
        marker = self.store.placeholder
        with self.store.transaction() as cursor:
            cursor.execute(
                f"SELECT key_id, role, status, created_at, expires_at, grace_until, "
                f"rotated_from, metadata FROM api_key_registry WHERE key_id = {marker}",
                (key_id,),
            )
            row = cursor.fetchone()
        return _registered_key(row) if row else None

    def hash_secret(self, raw_key: str) -> str:
        return hashlib.sha256(f"{self.pepper}:{raw_key}".encode()).hexdigest()

    @staticmethod
    def _usable(item: RegisteredKey, now: float) -> bool:
        if item.expires_at is not None and item.expires_at <= now:
            return False
        if item.status == "active":
            return True
        return item.status == "grace" and bool(item.grace_until and item.grace_until > now)


def _registered_key(row: Any) -> RegisteredKey:
    return RegisteredKey(
        key_id=str(row[0]),
        role=str(row[1]),
        status=str(row[2]),
        created_at=float(row[3]),
        expires_at=float(row[4]) if row[4] is not None else None,
        grace_until=float(row[5]) if row[5] is not None else None,
        rotated_from=str(row[6]) if row[6] is not None else None,
        metadata=json.loads(row[7]),
    )
