"""
Tests for the Auth0 wiring and the encrypted OAuth token store in server.py.

No real Auth0: a local OIDC discovery document stands in for the tenant, so the
real FastMCP Auth0Provider is constructed with SOMA's arguments (catching any
signature drift in a FastMCP upgrade) without network access.
"""

import json
import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fastmcp
import pytest
from cryptography.fernet import Fernet
from fastmcp.server.auth.providers.auth0 import Auth0Provider

from soma_mcp import server
from soma_mcp.config import TOKEN_STORE_DIRNAME, ConfigurationError, TokenStorage

SECRET = "client-secret-that-must-never-be-echoed"


@pytest.fixture
def oidc_config_url() -> Iterator[str]:
    """Serve a minimal OIDC discovery document on 127.0.0.1."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            issuer = f"http://127.0.0.1:{self.server.server_address[1]}/"
            body = json.dumps({
                "issuer": issuer,
                "authorization_endpoint": issuer + "authorize",
                "token_endpoint": issuer + "oauth/token",
                "jwks_uri": issuer + ".well-known/jwks.json",
                "response_types_supported": ["code"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/.well-known/openid-configuration"
    httpd.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def auth_env(monkeypatch, oidc_config_url, tmp_path):
    # FastMCP's default OAuth store (used when SOMA's own storage is not
    # configured) lives under fastmcp.settings.home; keep it out of $HOME.
    monkeypatch.setattr(fastmcp.settings, "home", Path(tmp_path) / "fastmcp-home")
    monkeypatch.setenv("AUTH0_CONFIG_URL", oidc_config_url)
    monkeypatch.setenv("AUTH0_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.test/")
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:8000/")


def _storage(tmp_path: Path, key: bytes | None = None) -> TokenStorage:
    return TokenStorage(directory=Path(tmp_path) / TOKEN_STORE_DIRNAME,
                        jwt_signing_key="a-long-test-signing-key",
                        encryption_key=(key or Fernet.generate_key()).decode())


def test_no_auth_configured_builds_an_unauthenticated_server():
    assert server.build_server().auth is None


def test_partial_auth_refuses_to_build(monkeypatch):
    monkeypatch.setenv("AUTH0_CONFIG_URL", "https://tenant.example/.well-known/openid-configuration")
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", SECRET)
    with pytest.raises(ConfigurationError) as exc:
        server.build_server()
    assert SECRET not in str(exc.value)


def test_complete_auth_constructs_auth0_provider(auth_env):
    mcp = server.build_server()
    assert isinstance(mcp.auth, Auth0Provider)


def test_persistent_storage_uses_encrypted_filetree_on_the_data_volume(
        auth_env, monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_JWT_SIGNING_KEY", "a-long-test-signing-key")
    monkeypatch.setenv("MCP_STORAGE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    mcp = server.build_server()
    assert isinstance(mcp.auth, Auth0Provider)
    assert (Path(tmp_path) / TOKEN_STORE_DIRNAME).is_dir()


def test_invalid_encryption_key_fails_clearly_without_echoing_it(auth_env, monkeypatch):
    monkeypatch.setenv("MCP_JWT_SIGNING_KEY", "a-long-test-signing-key")
    monkeypatch.setenv("MCP_STORAGE_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(ConfigurationError, match="MCP_STORAGE_ENCRYPTION_KEY") as exc:
        server.build_server()
    assert "not-a-fernet-key" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_legacy_diskstore_directory_is_reported_not_read(auth_env, monkeypatch, tmp_path, caplog):
    legacy = Path(tmp_path) / "mcp_tokens"
    legacy.mkdir()
    (legacy / "cache.db").write_bytes(b"pickle data that must never be loaded")
    monkeypatch.setenv("MCP_JWT_SIGNING_KEY", "a-long-test-signing-key")
    monkeypatch.setenv("MCP_STORAGE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with caplog.at_level(logging.WARNING, logger="soma_mcp"):
        server.build_server()
    assert "pre-0.2 DiskStore" in caplog.text
    assert (legacy / "cache.db").read_bytes().startswith(b"pickle data")


@pytest.mark.anyio
async def test_token_store_is_encrypted_at_rest_and_survives_restart(tmp_path):
    key = Fernet.generate_key()
    store = server._token_storage(_storage(tmp_path, key))
    await store.put(key="https://claude.ai/oauth/client-metadata", collection="clients",
                    value={"refresh_token": "plaintext-refresh-token"})

    files = [p for p in (Path(tmp_path) / TOKEN_STORE_DIRNAME).rglob("*") if p.is_file()]
    assert files, "nothing was persisted"
    for path in files:
        assert b"plaintext-refresh-token" not in path.read_bytes()
        assert "claude.ai" not in str(path)  # URL-shaped keys are sanitized, not used as paths

    restarted = server._token_storage(_storage(tmp_path, key))
    value = await restarted.get(key="https://claude.ai/oauth/client-metadata",
                                collection="clients")
    assert value == {"refresh_token": "plaintext-refresh-token"}


@pytest.mark.anyio
async def test_wrong_key_reads_as_missing_never_as_plaintext(tmp_path):
    first = server._token_storage(_storage(tmp_path))
    await first.put(key="client", collection="clients", value={"token": "t"})
    rotated = server._token_storage(_storage(tmp_path))  # a different random key
    assert await rotated.get(key="client", collection="clients") is None
