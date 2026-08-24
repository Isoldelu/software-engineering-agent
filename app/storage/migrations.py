"""Versioned and checksum-protected control-plane schema migrations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


class MigrationChecksumError(RuntimeError):
    """Raised when an applied migration no longer matches the source definition."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        source = f"{self.version}:{self.name}:" + "\n".join(self.statements)
        return hashlib.sha256(source.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(
        version=1,
        name="control_plane_records_and_leases",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS control_plane_records (
                namespace TEXT NOT NULL,
                record_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (namespace, record_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS control_plane_leases (
                name TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL
            )
            """,
        ),
    ),
    Migration(
        version=2,
        name="api_key_registry_and_audit",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS api_key_registry (
                key_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                secret_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION,
                grace_until DOUBLE PRECISION,
                rotated_from TEXT,
                metadata TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS control_plane_audit (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                actor_fingerprint TEXT,
                actor_role TEXT,
                resource TEXT NOT NULL,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
        ),
    ),
    Migration(
        version=3,
        name="retention_and_lookup_indexes",
        statements=(
            """
            CREATE INDEX IF NOT EXISTS idx_control_plane_records_retention
            ON control_plane_records (namespace, updated_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_control_plane_audit_created_at
            ON control_plane_audit (created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_api_key_registry_role_status
            ON api_key_registry (role, status)
            """,
        ),
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
SCHEMA_LOCK_ID = 8_104_227_027


def apply_migrations(store: Any) -> dict[str, object]:
    """Apply pending migrations in one transaction and verify prior checksums."""
    marker = store.placeholder
    scheme = store.scheme
    with store.transaction(write=True) as cursor:
        if scheme == "postgresql":
            cursor.execute(f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK_ID})")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS control_plane_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at DOUBLE PRECISION NOT NULL
            )
            """
        )
        cursor.execute(
            "SELECT version, name, checksum FROM control_plane_schema_migrations "
            "ORDER BY version"
        )
        applied = {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
        applied_now: list[int] = []
        for migration in MIGRATIONS:
            recorded = applied.get(migration.version)
            if recorded:
                if recorded != (migration.name, migration.checksum):
                    raise MigrationChecksumError(
                        f"Migration {migration.version} checksum/name mismatch."
                    )
                continue
            for statement in migration.statements:
                cursor.execute(statement)
            import time

            cursor.execute(
                f"INSERT INTO control_plane_schema_migrations "
                f"(version, name, checksum, applied_at) "
                f"VALUES ({marker}, {marker}, {marker}, {marker})",
                (migration.version, migration.name, migration.checksum, time.time()),
            )
            applied_now.append(migration.version)
    return {
        "current_version": LATEST_SCHEMA_VERSION,
        "latest_version": LATEST_SCHEMA_VERSION,
        "applied_now": applied_now,
        "up_to_date": True,
    }
