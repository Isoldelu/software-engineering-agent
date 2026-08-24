"""PostgreSQL/SQLite JSON record store with CAS updates and distributed leases."""

from __future__ import annotations

import builtins
import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.storage.migrations import LATEST_SCHEMA_VERSION, apply_migrations

DATABASE_URL_ENV = "SOFTWARE_AGENT_DATABASE_URL"
SUPPORTED_SCHEMES = {"sqlite", "postgresql", "postgres"}


class ConcurrentUpdateError(RuntimeError):
    """Raised when a compare-and-swap revision no longer matches."""


class LeaseUnavailableError(RuntimeError):
    """Raised when another process owns a non-expired database lease."""


@dataclass(frozen=True)
class StoredRecord:
    namespace: str
    record_id: str
    payload: dict[str, Any]
    version: int
    updated_at: float


class ControlPlaneStore:
    """Small shared control-plane store using standard SQL transactions."""

    def __init__(
        self,
        database_url: str,
        *,
        connect_timeout: float = 3.0,
        pool_enabled: bool | None = None,
        pool_min_size: int | None = None,
        pool_max_size: int | None = None,
    ) -> None:
        parsed = urlparse(database_url)
        if parsed.scheme not in SUPPORTED_SCHEMES:
            expected = ", ".join(sorted(SUPPORTED_SCHEMES))
            raise ValueError(f"Unsupported database scheme. Expected one of: {expected}.")
        self.database_url = database_url
        self.scheme = "postgresql" if parsed.scheme in {"postgres", "postgresql"} else "sqlite"
        self.connect_timeout = connect_timeout
        self.sqlite_path = _sqlite_path(parsed) if self.scheme == "sqlite" else None
        requested_pool = (
            _env_bool("SOFTWARE_AGENT_DB_POOL_ENABLED", default=True)
            if pool_enabled is None
            else pool_enabled
        )
        self.pool_enabled = self.scheme == "postgresql" and requested_pool
        self.pool_min_size = pool_min_size or _env_int(
            "SOFTWARE_AGENT_DB_POOL_MIN_SIZE", default=1, minimum=1
        )
        self.pool_max_size = pool_max_size or _env_int(
            "SOFTWARE_AGENT_DB_POOL_MAX_SIZE", default=10, minimum=1
        )
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("Database pool min size cannot exceed max size.")
        self._pool: Any | None = self._build_pool() if self.pool_enabled else None
        self.migration_status: dict[str, object] = {}
        try:
            self.initialize()
        except Exception:
            self.close()
            raise

    @property
    def placeholder(self) -> str:
        return "%s" if self.scheme == "postgresql" else "?"

    def initialize(self) -> None:
        self.migration_status = apply_migrations(self)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Any]:
        """Expose a backend-neutral transaction to control-plane repositories."""
        with self._transaction(write=write) as cursor:
            yield cursor

    def upsert(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> StoredRecord:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        now = time.time()
        marker = self.placeholder
        with self._transaction(write=True) as cursor:
            cursor.execute(
                f"SELECT version FROM control_plane_records "
                f"WHERE namespace = {marker} AND record_id = {marker}",
                (namespace, record_id),
            )
            row = cursor.fetchone()
            current_version = int(row[0]) if row else 0
            if expected_version is not None and expected_version != current_version:
                raise ConcurrentUpdateError(
                    f"Revision conflict for {namespace}/{record_id}: "
                    f"expected {expected_version}, found {current_version}."
                )
            next_version = current_version + 1
            if row:
                cursor.execute(
                    f"UPDATE control_plane_records SET payload = {marker}, "
                    f"version = {marker}, updated_at = {marker} "
                    f"WHERE namespace = {marker} AND record_id = {marker}",
                    (serialized, next_version, now, namespace, record_id),
                )
            else:
                cursor.execute(
                    f"INSERT INTO control_plane_records "
                    f"(namespace, record_id, payload, version, updated_at) "
                    f"VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
                    (namespace, record_id, serialized, next_version, now),
                )
        return StoredRecord(namespace, record_id, payload, next_version, now)

    def get(self, namespace: str, record_id: str) -> StoredRecord | None:
        marker = self.placeholder
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT payload, version, updated_at FROM control_plane_records "
                f"WHERE namespace = {marker} AND record_id = {marker}",
                (namespace, record_id),
            )
            row = cursor.fetchone()
        return _stored_record(namespace, record_id, row) if row else None

    def list(self, namespace: str) -> list[StoredRecord]:
        marker = self.placeholder
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT record_id, payload, version, updated_at "
                f"FROM control_plane_records WHERE namespace = {marker} "
                f"ORDER BY updated_at, record_id",
                (namespace,),
            )
            rows = cursor.fetchall()
        return [
            StoredRecord(
                namespace=namespace,
                record_id=str(row[0]),
                payload=json.loads(row[1]),
                version=int(row[2]),
                updated_at=float(row[3]),
            )
            for row in rows
        ]

    def count(self, namespace: str) -> int:
        marker = self.placeholder
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM control_plane_records WHERE namespace = {marker}",
                (namespace,),
            )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def namespaces(self) -> builtins.list[str]:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT DISTINCT namespace FROM control_plane_records ORDER BY namespace"
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def delete_namespace(self, namespace: str) -> int:
        marker = self.placeholder
        with self._transaction(write=True) as cursor:
            cursor.execute(
                f"DELETE FROM control_plane_records WHERE namespace = {marker}",
                (namespace,),
            )
            return max(0, int(cursor.rowcount))

    def delete(
        self,
        namespace: str,
        record_id: str,
        *,
        expected_version: int | None = None,
    ) -> bool:
        marker = self.placeholder
        with self._transaction(write=True) as cursor:
            if expected_version is None:
                cursor.execute(
                    f"DELETE FROM control_plane_records "
                    f"WHERE namespace = {marker} AND record_id = {marker}",
                    (namespace, record_id),
                )
            else:
                cursor.execute(
                    f"DELETE FROM control_plane_records "
                    f"WHERE namespace = {marker} AND record_id = {marker} "
                    f"AND version = {marker}",
                    (namespace, record_id, expected_version),
                )
            return cursor.rowcount == 1

    def count_older_than(self, namespace: str, older_than: float) -> int:
        marker = self.placeholder
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM control_plane_records "
                f"WHERE namespace = {marker} AND updated_at < {marker}",
                (namespace, older_than),
            )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def prune_older_than(
        self,
        namespace: str,
        older_than: float,
        *,
        limit: int = 1000,
        dry_run: bool = False,
    ) -> int:
        """Delete a bounded oldest-record batch with portable SQL."""
        marker = self.placeholder
        bounded_limit = max(1, min(int(limit), 10_000))
        with self._transaction(write=not dry_run) as cursor:
            cursor.execute(
                f"SELECT record_id FROM control_plane_records "
                f"WHERE namespace = {marker} AND updated_at < {marker} "
                f"ORDER BY updated_at, record_id LIMIT {marker}",
                (namespace, older_than, bounded_limit),
            )
            record_ids = [str(row[0]) for row in cursor.fetchall()]
            if dry_run:
                return len(record_ids)
            for record_id in record_ids:
                cursor.execute(
                    f"DELETE FROM control_plane_records "
                    f"WHERE namespace = {marker} AND record_id = {marker}",
                    (namespace, record_id),
                )
        return len(record_ids)

    def acquire_lease(
        self,
        name: str,
        owner: str,
        *,
        ttl_seconds: float = 30.0,
    ) -> bool:
        now = time.time()
        expires_at = now + ttl_seconds
        marker = self.placeholder
        with self._transaction(write=True) as cursor:
            suffix = " FOR UPDATE" if self.scheme == "postgresql" else ""
            cursor.execute(
                f"SELECT owner, expires_at FROM control_plane_leases "
                f"WHERE name = {marker}{suffix}",
                (name,),
            )
            row = cursor.fetchone()
            if row and str(row[0]) != owner and float(row[1]) > now:
                return False
            if row:
                cursor.execute(
                    f"UPDATE control_plane_leases SET owner = {marker}, expires_at = {marker} "
                    f"WHERE name = {marker}",
                    (owner, expires_at, name),
                )
            else:
                cursor.execute(
                    f"INSERT INTO control_plane_leases (name, owner, expires_at) "
                    f"VALUES ({marker}, {marker}, {marker})",
                    (name, owner, expires_at),
                )
        return True

    def release_lease(self, name: str, owner: str) -> bool:
        marker = self.placeholder
        with self._transaction(write=True) as cursor:
            cursor.execute(
                f"DELETE FROM control_plane_leases "
                f"WHERE name = {marker} AND owner = {marker}",
                (name, owner),
            )
            return cursor.rowcount == 1

    @contextmanager
    def lease(
        self,
        name: str,
        owner: str,
        *,
        ttl_seconds: float = 30.0,
        wait_timeout: float = 0.0,
        poll_interval: float = 0.02,
    ) -> Iterator[None]:
        deadline = time.monotonic() + max(0.0, wait_timeout)
        while not self.acquire_lease(name, owner, ttl_seconds=ttl_seconds):
            if time.monotonic() >= deadline:
                raise LeaseUnavailableError(f"Lease is held by another worker: {name}")
            time.sleep(max(0.001, poll_interval))
        try:
            yield
        finally:
            self.release_lease(name, owner)

    def status(self) -> dict[str, Any]:
        healthy = False
        error_type = None
        try:
            with self._transaction() as cursor:
                cursor.execute("SELECT 1")
                healthy = bool(cursor.fetchone())
        except Exception as exc:  # noqa: BLE001 - optional drivers have distinct errors
            error_type = type(exc).__name__
        parsed = urlparse(self.database_url)
        target = (
            f"{parsed.hostname or 'localhost'}:{parsed.port or 5432}{parsed.path}"
            if self.scheme == "postgresql"
            else str(self.sqlite_path)
        )
        return {
            "enabled": True,
            "backend": self.scheme,
            "target": target,
            "healthy": healthy,
            "error_type": error_type,
            "schema_version": f"control-plane-v{LATEST_SCHEMA_VERSION}",
            "migration": self.migration_status,
            "pool": self.pool_status(),
            "credentials_exposed": False,
        }

    def pool_status(self) -> dict[str, Any]:
        if not self._pool:
            return {
                "enabled": False,
                "min_size": None,
                "max_size": None,
                "pool_size": None,
                "pool_available": None,
                "requests_waiting": None,
            }
        stats = self._pool.get_stats()
        return {
            "enabled": True,
            "min_size": self.pool_min_size,
            "max_size": self.pool_max_size,
            "pool_size": stats.get("pool_size"),
            "pool_available": stats.get("pool_available"),
            "requests_waiting": stats.get("requests_waiting"),
        }

    def close(self) -> None:
        """Close this process's PostgreSQL pool."""
        if self._pool:
            self._pool.close()

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[Any]:
        with self._connection() as connection:
            cursor = connection.cursor()
            try:
                if self.scheme == "sqlite":
                    cursor.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pool:
            with self._pool.connection(timeout=self.connect_timeout) as connection:
                yield connection
            return
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _connect(self) -> Any:
        if self.scheme == "sqlite":
            if self.sqlite_path is None:
                raise RuntimeError("SQLite path is missing.")
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.sqlite_path,
                timeout=self.connect_timeout,
                isolation_level=None,
            )
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(f"PRAGMA busy_timeout={int(self.connect_timeout * 1000)}")
            return connection
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL persistence requires psycopg; install requirements-runtime.txt."
            ) from exc
        return psycopg.connect(
            self.database_url,
            connect_timeout=max(1, int(self.connect_timeout)),
        )

    def _build_pool(self) -> Any:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL pooling requires psycopg_pool; install requirements-runtime.txt."
            ) from exc
        return ConnectionPool(
            conninfo=self.database_url,
            min_size=self.pool_min_size,
            max_size=self.pool_max_size,
            timeout=self.connect_timeout,
            kwargs={"connect_timeout": max(1, int(self.connect_timeout))},
            open=True,
        )


def build_store_from_env() -> ControlPlaneStore | None:
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    return ControlPlaneStore(database_url) if database_url else None


def storage_status(store: ControlPlaneStore | None) -> dict[str, Any]:
    if store is None:
        return {
            "enabled": False,
            "backend": "memory",
            "target": None,
            "healthy": True,
            "error_type": None,
            "schema_version": f"control-plane-v{LATEST_SCHEMA_VERSION}",
            "migration": {
                "current_version": None,
                "latest_version": LATEST_SCHEMA_VERSION,
                "applied_now": [],
                "up_to_date": True,
            },
            "pool": {
                "enabled": False,
                "min_size": None,
                "max_size": None,
                "pool_size": None,
                "pool_available": None,
                "requests_waiting": None,
            },
            "credentials_exposed": False,
        }
    return store.status()


def _sqlite_path(parsed: Any) -> Path:
    raw_path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"//{parsed.netloc}{raw_path}"
    if (
        os.name == "nt"
        and raw_path.startswith("/")
        and len(raw_path) > 2
        and raw_path[2] == ":"
    ):
        raw_path = raw_path[1:]
    if not raw_path or raw_path == "/":
        raise ValueError("SQLite database URL must include a file path.")
    return Path(raw_path).resolve()


def _stored_record(namespace: str, record_id: str, row: Any) -> StoredRecord:
    return StoredRecord(
        namespace=namespace,
        record_id=record_id,
        payload=json.loads(row[0]),
        version=int(row[1]),
        updated_at=float(row[2]),
    )


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int, minimum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return parsed


DEFAULT_CONTROL_PLANE_STORE = build_store_from_env()
