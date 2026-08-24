"""Environment-backed role-aware API Key authentication."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any

from app.security.key_registry import KeyRegistry
from app.storage.database import DEFAULT_CONTROL_PLANE_STORE, ControlPlaneStore

API_KEY_HEADER = "X-API-Key"
ROLE_RANK = {"reader": 1, "operator": 2, "admin": 3}
KEY_ENVIRONMENTS = {
    "reader": "SOFTWARE_AGENT_READER_API_KEY",
    "operator": "SOFTWARE_AGENT_OPERATOR_API_KEY",
    "admin": "SOFTWARE_AGENT_ADMIN_API_KEY",
}
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/auth/status",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
    "/demo",
}


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    keys: dict[str, str]

    @classmethod
    def from_env(cls) -> AuthSettings:
        return cls(
            enabled=_env_bool("SOFTWARE_AGENT_AUTH_ENABLED", default=False),
            keys={
                role: value
                for role, name in KEY_ENVIRONMENTS.items()
                if (value := os.getenv(name, "").strip())
            },
        )

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "header": API_KEY_HEADER,
            "configured_roles": sorted(self.keys, key=lambda role: ROLE_RANK[role]),
            "role_hierarchy": ["reader", "operator", "admin"],
            "secrets_exposed": False,
        }


@dataclass(frozen=True)
class AuthPrincipal:
    role: str
    key_fingerprint: str | None
    authentication_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "key_fingerprint": self.key_fingerprint,
            "authentication_enabled": self.authentication_enabled,
        }


class ApiKeyAuthenticator:
    def __init__(self, store: ControlPlaneStore | None = DEFAULT_CONTROL_PLANE_STORE) -> None:
        self.registry = KeyRegistry(store) if store is not None else None

    def authenticate(
        self,
        provided_key: str | None,
        *,
        required_role: str,
        settings: AuthSettings | None = None,
    ) -> AuthPrincipal:
        current = settings or AuthSettings.from_env()
        if not current.enabled:
            return AuthPrincipal("anonymous", None, False)
        if required_role not in ROLE_RANK:
            raise ValueError(f"Unknown required role: {required_role}")
        managed_roles = self.registry.managed_roles() if self.registry else set()
        if not current.keys and not managed_roles:
            raise AuthConfigurationError("Authentication is enabled but no API Keys are configured.")
        if not provided_key:
            raise AuthenticationError("API Key is required.")

        matched_role = None
        if self.registry:
            registered = self.registry.authenticate(provided_key)
            if registered:
                matched_role = registered.role
        for role in ("admin", "operator", "reader"):
            if matched_role or role in managed_roles:
                continue
            configured = current.keys.get(role)
            if configured and secrets.compare_digest(provided_key, configured):
                matched_role = role
                break
        if not matched_role:
            raise AuthenticationError("API Key is invalid.")
        if ROLE_RANK[matched_role] < ROLE_RANK[required_role]:
            raise AuthorizationError(
                f"Role '{matched_role}' cannot access a '{required_role}' endpoint."
            )
        return AuthPrincipal(
            role=matched_role,
            key_fingerprint=hashlib.sha256(provided_key.encode("utf-8")).hexdigest()[:12],
            authentication_enabled=True,
        )


class AuthenticationError(PermissionError):
    pass


class AuthorizationError(PermissionError):
    pass


class AuthConfigurationError(RuntimeError):
    pass


def required_role(method: str, path: str) -> str | None:
    if method.upper() == "OPTIONS" or path in PUBLIC_PATHS:
        return None
    normalized_method = method.upper()
    if path.startswith(("/auth/keys", "/audit", "/maintenance")):
        return "admin"
    if normalized_method == "DELETE":
        return "admin"
    if normalized_method in {"POST", "PUT", "PATCH"}:
        if (
            path.startswith("/policies/")
            or path.endswith(("/review", "/activate"))
        ):
            return "admin"
        return "operator"
    return "reader"


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
