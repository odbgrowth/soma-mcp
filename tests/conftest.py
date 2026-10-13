"""Shared fixtures: a clean configuration environment per test, and a real
Streamable HTTP server on 127.0.0.1 for transport-level tests.

Nothing here needs Auth0, real SOMA data or internet access.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import fastmcp
import pytest
import uvicorn

import soma_mcp.guard as guard

# Every variable the server reads. Cleared per test so a developer's shell or a
# CI runner can never leak configuration (or credentials) into a test.
CONFIG_ENV = (
    "AUTH0_CONFIG_URL", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "AUTH0_AUDIENCE",
    "BASE_URL", "MCP_JWT_SIGNING_KEY", "MCP_STORAGE_ENCRYPTION_KEY",
    "MCP_TOEGANG_SUBJECTS", "MCP_SCHRIJF_SUBJECTS", "MCP_SINGLE_USER", "MCP_RATE_LIMIT",
    "MCP_HOST", "MCP_PORT", "SOMA_DATA",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    for name in CONFIG_ENV:
        monkeypatch.delenv(name, raising=False)
    # Audit log and token store land in a per-test directory, never in the repo.
    monkeypatch.setenv("SOMA_DATA", str(tmp_path))
    guard._calls.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class HttpServer:
    """A running Streamable HTTP server plus every response body it sent."""

    url: str
    bodies: list[bytes] = field(default_factory=list)

    @property
    def wire(self) -> str:
        return b"".join(self.bodies).decode("utf-8", errors="replace")


@pytest.fixture
def serve_http() -> Iterator[Callable[..., HttpServer]]:
    """Factory: serve a FastMCP server over real HTTP on 127.0.0.1.

    Keyword arguments go to `mcp.http_app()` (for example the Host/Origin guard
    settings `serve()` uses). The ASGI app is wrapped so the test can assert on
    the exact bytes that went over the wire. The socket is bound here and handed
    to uvicorn, so no other process can grab the port in between.
    """
    servers: list[tuple[uvicorn.Server, threading.Thread, socket.socket]] = []

    def start(mcp: Any, **http_app_options: Any) -> HttpServer:
        app = mcp.http_app(**http_app_options)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
        result = HttpServer(url=f"http://127.0.0.1:{port}/mcp")

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:
            async def capture(message: Any) -> None:
                if message["type"] == "http.response.body":
                    result.bodies.append(message.get("body", b""))
                await send(message)

            await app(scope, receive, capture if scope["type"] == "http" else send)

        server = uvicorn.Server(uvicorn.Config(
            capturing_app, log_level="warning", lifespan="on"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if time.monotonic() > deadline or not thread.is_alive():
                raise RuntimeError("test HTTP server did not start")
            time.sleep(0.02)
        servers.append((server, thread, sock))
        return result

    yield start

    for server, thread, sock in servers:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


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
def auth_env(monkeypatch: pytest.MonkeyPatch, oidc_config_url: str, tmp_path: Any) -> None:
    """A complete Auth0 configuration against the local OIDC discovery document."""
    # FastMCP's default OAuth store (used when SOMA's own storage is not
    # configured) lives under fastmcp.settings.home; keep it out of $HOME.
    monkeypatch.setattr(fastmcp.settings, "home", Path(tmp_path) / "fastmcp-home")
    monkeypatch.setenv("AUTH0_CONFIG_URL", oidc_config_url)
    monkeypatch.setenv("AUTH0_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", "client-secret-that-must-never-be-echoed")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.test/")
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:8000/")
