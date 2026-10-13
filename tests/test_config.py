"""
Tests for config.py: authentication, token storage and bind address are
all-or-nothing and fail closed. A missing variable must never downgrade the
server to an unauthenticated or non-persistent mode silently.
"""

from pathlib import Path

import pytest

from soma_mcp.config import (
    AUTH0_VARS,
    STORAGE_VARS,
    TOKEN_STORE_DIRNAME,
    ConfigurationError,
    bind_address,
    is_loopback,
    load_auth_config,
)

SECRET = "s3cret-value-that-must-never-be-echoed"

FULL_AUTH = {
    "AUTH0_CONFIG_URL": "https://tenant.example/.well-known/openid-configuration",
    "AUTH0_CLIENT_ID": "client-id",
    "AUTH0_CLIENT_SECRET": SECRET,
    "AUTH0_AUDIENCE": "https://api.example/",
    "BASE_URL": "https://mcp.example/",
}
FULL_STORAGE = {
    "MCP_JWT_SIGNING_KEY": SECRET + "-jwt",
    "MCP_STORAGE_ENCRYPTION_KEY": SECRET + "-fernet",
}


def test_no_auth_configured_means_local_mode():
    assert load_auth_config({}) is None
    assert load_auth_config({"BASE_URL": "https://mcp.example/"}) is None


@pytest.mark.parametrize("missing", [*AUTH0_VARS, "BASE_URL"])
def test_partial_auth_refuses_to_start(missing):
    env = {k: v for k, v in FULL_AUTH.items() if k != missing}
    with pytest.raises(ConfigurationError) as exc:
        load_auth_config(env)
    assert missing in str(exc.value)
    assert SECRET not in str(exc.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_value_counts_as_missing(blank):
    env = {**FULL_AUTH, "AUTH0_AUDIENCE": blank}
    with pytest.raises(ConfigurationError, match="AUTH0_AUDIENCE"):
        load_auth_config(env)


def test_single_auth0_variable_is_partial_not_local():
    """Setting only the secret must not fall back to the unauthenticated server."""
    with pytest.raises(ConfigurationError):
        load_auth_config({"AUTH0_CLIENT_SECRET": SECRET})


def test_complete_auth_without_storage():
    config = load_auth_config(FULL_AUTH)
    assert config is not None
    assert config.client_secret == SECRET
    assert config.storage is None
    assert SECRET not in repr(config)


def test_complete_auth_with_storage(tmp_path):
    config = load_auth_config({**FULL_AUTH, **FULL_STORAGE, "SOMA_DATA": str(tmp_path)})
    assert config is not None and config.storage is not None
    assert config.storage.directory == Path(tmp_path) / TOKEN_STORE_DIRNAME
    assert config.storage.jwt_signing_key == FULL_STORAGE["MCP_JWT_SIGNING_KEY"]
    assert SECRET not in repr(config)


@pytest.mark.parametrize("present", STORAGE_VARS)
def test_partial_storage_refuses_to_start(present):
    env = {**FULL_AUTH, present: FULL_STORAGE[present]}
    with pytest.raises(ConfigurationError) as exc:
        load_auth_config(env)
    assert SECRET not in str(exc.value)


def test_storage_without_auth_refuses_to_start():
    with pytest.raises(ConfigurationError, match="Auth0 is not configured"):
        load_auth_config(FULL_STORAGE)


def test_unauthenticated_server_binds_loopback_by_default():
    assert bind_address({}, authenticated=False) == ("127.0.0.1", 8000)


def test_authenticated_server_binds_all_interfaces_by_default():
    assert bind_address({}, authenticated=True) == ("0.0.0.0", 8000)


def test_bind_overrides():
    env = {"MCP_HOST": "::1", "MCP_PORT": "9001"}
    assert bind_address(env, authenticated=False) == ("::1", 9001)


@pytest.mark.parametrize("port", ["http", "0", "65536", "-1"])
def test_invalid_port_refuses_to_start(port):
    with pytest.raises(ConfigurationError, match="MCP_PORT"):
        bind_address({"MCP_PORT": port}, authenticated=False)


@pytest.mark.parametrize(("host", "expected"), [
    ("127.0.0.1", True), ("127.1.2.3", True), ("::1", True), ("localhost", True),
    ("0.0.0.0", False), ("::", False), ("192.168.1.10", False), ("example.com", False),
])
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected
