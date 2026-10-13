"""Shared fixtures: a clean configuration environment per test, and a real
Streamable HTTP server on 127.0.0.1 for transport-level tests.

Nothing here needs Auth0, real SOMA data or internet access.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def serve_http() -> Iterator[Callable[[Any], HttpServer]]:
    """Factory: serve a FastMCP server over real HTTP on 127.0.0.1.

    The ASGI app is wrapped so the test can assert on the exact bytes that went
    over the wire (camelCase field names, fenced memory text, masked errors).
    """
    servers: list[tuple[uvicorn.Server, threading.Thread]] = []

    def start(mcp: Any) -> HttpServer:
        app = mcp.http_app()
        port = _free_port()
        result = HttpServer(url=f"http://127.0.0.1:{port}/mcp")

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:
            async def capture(message: Any) -> None:
                if message["type"] == "http.response.body":
                    result.bodies.append(message.get("body", b""))
                await send(message)

            await app(scope, receive, capture if scope["type"] == "http" else send)

        server = uvicorn.Server(uvicorn.Config(
            capturing_app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            if time.monotonic() > deadline or not thread.is_alive():
                raise RuntimeError("test HTTP server did not start")
            time.sleep(0.02)
        servers.append((server, thread))
        return result

    yield start

    for server, thread in servers:
        server.should_exit = True
        thread.join(timeout=10)
