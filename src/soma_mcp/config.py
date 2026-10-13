"""
config.py: environment configuration for the transport shell, FastMCP-free.

Every setting that decides whether the server authenticates, where it stores
OAuth state, and which interface it listens on is read here, from explicit
environment variables only. The rules fail closed:

* Auth0 is all-or-nothing. Setting some AUTH0_* variables but not all of them
  (or omitting BASE_URL) raises ConfigurationError instead of silently starting
  an unauthenticated server.
* Persistent token storage is all-or-nothing too, and only valid with Auth0.
* Without authentication the HTTP server binds to loopback unless MCP_HOST says
  otherwise, so a local experiment is not reachable from the network by accident.

Error messages name variables, never their values. Secret fields are excluded
from the dataclass reprs so a logged config object cannot leak them.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

AUTH0_VARS = ("AUTH0_CONFIG_URL", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "AUTH0_AUDIENCE")
STORAGE_VARS = ("MCP_JWT_SIGNING_KEY", "MCP_STORAGE_ENCRYPTION_KEY")

# Encrypted FileTreeStore (0.2.0+). A new directory name on purpose: the pre-0.2
# pickle-based DiskStore lived in "mcp_tokens" and is never read again.
TOKEN_STORE_DIRNAME = "mcp_oauth"  # noqa: S105 - a directory name, not a secret
LEGACY_TOKEN_STORE_DIRNAME = "mcp_tokens"  # noqa: S105 - a directory name

DEFAULT_PORT = 8000
LOOPBACK_HOST = "127.0.0.1"
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - only the default when OAuth is configured


class ConfigurationError(RuntimeError):
    """The environment describes a partial or unsafe setup; refuse to start."""


@dataclass(frozen=True)
class TokenStorage:
    """Where and how issued OAuth state is persisted (encrypted at rest)."""

    directory: Path
    jwt_signing_key: str = field(repr=False)
    encryption_key: str = field(repr=False)


@dataclass(frozen=True)
class AuthConfig:
    """A complete Auth0 configuration, plus optional persistent token storage."""

    config_url: str
    client_id: str
    audience: str
    base_url: str
    client_secret: str = field(repr=False)
    storage: TokenStorage | None = None


def _is_set(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def data_dir(env: Mapping[str, str] | None = None) -> Path:
    """The data volume (token store, audit log). Defaults to the working dir."""
    env = os.environ if env is None else env
    return Path(env.get("SOMA_DATA", "").strip() or ".")


def load_auth_config(env: Mapping[str, str] | None = None) -> AuthConfig | None:
    """Return the Auth0 configuration, None for local unauthenticated mode, or
    raise ConfigurationError when the variables describe a partial setup."""
    env = os.environ if env is None else env
    auth_set = [name for name in AUTH0_VARS if _is_set(env, name)]
    storage_set = [name for name in STORAGE_VARS if _is_set(env, name)]

    if not auth_set:
        if storage_set:
            raise ConfigurationError(
                f"{', '.join(storage_set)} set but Auth0 is not configured. Token storage "
                f"only applies to an authenticated server: set all of "
                f"{', '.join(AUTH0_VARS)} and BASE_URL, or unset the storage variables."
            )
        return None

    missing = [name for name in (*AUTH0_VARS, "BASE_URL") if not _is_set(env, name)]
    if missing:
        raise ConfigurationError(
            f"incomplete Auth0 configuration: {', '.join(missing)} not set. Set all of "
            f"{', '.join(AUTH0_VARS)} and BASE_URL, or none of the AUTH0_* variables "
            f"to run the local, unauthenticated reference server."
        )

    storage = None
    if storage_set:
        missing_storage = [name for name in STORAGE_VARS if not _is_set(env, name)]
        if missing_storage:
            raise ConfigurationError(
                f"incomplete token storage configuration: {', '.join(missing_storage)} "
                f"not set. Set both {' and '.join(STORAGE_VARS)} for encrypted, "
                f"persistent token storage, or neither."
            )
        storage = TokenStorage(
            directory=data_dir(env) / TOKEN_STORE_DIRNAME,
            jwt_signing_key=env["MCP_JWT_SIGNING_KEY"],
            encryption_key=env["MCP_STORAGE_ENCRYPTION_KEY"],
        )

    return AuthConfig(
        config_url=env["AUTH0_CONFIG_URL"],
        client_id=env["AUTH0_CLIENT_ID"],
        client_secret=env["AUTH0_CLIENT_SECRET"],
        audience=env["AUTH0_AUDIENCE"],
        base_url=env["BASE_URL"],
        storage=storage,
    )


def bind_address(env: Mapping[str, str] | None = None, *, authenticated: bool) -> tuple[str, int]:
    """Return (host, port) for the HTTP transport.

    MCP_HOST/MCP_PORT override the defaults. Without them an authenticated
    server listens on all interfaces (it normally runs in a container behind a
    TLS-terminating proxy) and an unauthenticated one only on loopback.
    """
    env = os.environ if env is None else env
    host = env.get("MCP_HOST", "").strip() or (ALL_INTERFACES if authenticated else LOOPBACK_HOST)
    raw_port = env.get("MCP_PORT", "").strip()
    if not raw_port:
        return host, DEFAULT_PORT
    try:
        port = int(raw_port)
    except ValueError:
        raise ConfigurationError("MCP_PORT must be an integer between 1 and 65535") from None
    if not 1 <= port <= 65535:
        raise ConfigurationError("MCP_PORT must be an integer between 1 and 65535")
    return host, port


def is_loopback(host: str) -> bool:
    """True if `host` only accepts connections from the local machine."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
