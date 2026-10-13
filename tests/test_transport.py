"""
Transport-level MCP tests: the FastMCP shell, not just the kernel behind it.

Dependency upgrades can leave the unit-tested kernel green while the protocol
surface breaks, so these drive the real server through the official clients:

* in memory through `fastmcp.Client`, on both protocol eras: the sessionless
  2026-07-28 revision (server/discover) and the handshake era (initialize);
* over real Streamable HTTP on 127.0.0.1 through the MCP Python SDK's `Client`,
  asserting the exact bytes on the wire (camelCase annotation hints).

No Auth0, no real SOMA data, no internet.
"""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest
from fastmcp import Client as FastMCPClient
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp import Client as SDKClient
from mcp.client.streamable_http import streamable_http_client
from mcp.types.version import LATEST_HANDSHAKE_VERSION, LATEST_MODERN_VERSION

import soma_mcp
from soma_mcp import server
from soma_mcp.engine import InMemoryEngine
from soma_mcp.instructions import ANNOTATIONS, build_instructions
from soma_mcp.kernel import _DATA_BOUNDARY

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ERAS = [("auto", LATEST_MODERN_VERSION), ("legacy", LATEST_HANDSHAKE_VERSION)]
WIRE_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


@pytest.fixture
def local_mode(monkeypatch):
    """The documented local quick start: no Auth0, deliberate single-user mode."""
    monkeypatch.setenv("MCP_SINGLE_USER", "1")
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")


def _payload(result: Any) -> Any:
    """A tool's structured result; FastMCP wraps non-object returns in {"result": ...}."""
    assert not result.is_error, result.content
    data = result.structured_content
    return data["result"] if set(data) == {"result"} else data


# What FastMCP 4.1 advertises for SOMA, pinned so a FastMCP upgrade that changes
# the wire surface fails here and the docs (specification.md §4) get updated.
# Only tools are populated; prompts and resources list empty.
CAPABILITIES = {
    "auto": {"logging": {}, "prompts": {"listChanged": False},
             "resources": {"subscribe": False, "listChanged": False},
             "tools": {"listChanged": False},
             "extensions": {"io.modelcontextprotocol/ui": {}}},
    "legacy": {"logging": {}, "prompts": {"listChanged": True},
               "resources": {"subscribe": False, "listChanged": True},
               "tools": {"listChanged": True}},
}


@pytest.mark.parametrize(("mode", "protocol"), ERAS)
async def test_discovery_identity_and_instructions(local_mode, mode, protocol):
    async with FastMCPClient(server.build_server(), mode=mode) as client:
        assert client.protocol_version == protocol
        assert client.server_info is not None
        assert client.server_info.name == "SOMA"
        assert client.server_info.version == soma_mcp.__version__
        assert client.instructions == build_instructions()
        assert client.server_capabilities is not None
        assert client.server_capabilities.model_dump(
            by_alias=True, exclude_none=True, mode="json") == CAPABILITIES[mode]
        assert await client.list_prompts() == []
        assert await client.list_resources() == []


@pytest.mark.parametrize(("mode", "protocol"), ERAS)
async def test_tools_list_schemas_and_annotations(local_mode, mode, protocol):
    async with FastMCPClient(server.build_server(), mode=mode) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == set(ANNOTATIONS)
    for name, tool in tools.items():
        assert tool.input_schema["type"] == "object"
        assert tool.description
        assert tool.annotations == ANNOTATIONS[name]
    assert tools["soma_delete"].input_schema["properties"]["confirm"]["default"] is False


@pytest.mark.parametrize(("mode", "protocol"), ERAS)
async def test_whoami_search_and_guarded_write(local_mode, mode, protocol):
    async with FastMCPClient(server.build_server(), mode=mode) as client:
        whoami = _payload(await client.call_tool("soma_whoami", {}))
        assert whoami == {"subject": None, "note": "unauthenticated reference server"}

        assert _payload(await client.call_tool("soma_search", {"query": "sky"})) == []
        saved = _payload(await client.call_tool("soma_write", {"text": "the sky is blue"}))
        assert saved == {"status": "saved", "chunks": 1}

        fenced = _DATA_BOUNDARY + "the sky is blue"
        hits = _payload(await client.call_tool("soma_search", {"query": "sky"}))
        assert hits[0]["tekst"] == fenced
        debug = _payload(await client.call_tool("soma_debug", {"query": "sky"}))
        assert debug["stage1_search"][0]["snippet"] == fenced

        preview = _payload(await client.call_tool("soma_delete", {"base_id": "note-ref-0001"}))
        assert preview["preview"] == fenced and "status" not in preview
        deleted = _payload(await client.call_tool(
            "soma_delete", {"base_id": "note-ref-0001", "confirm": True}))
        assert deleted["status"] == "deleted"


async def test_every_tool_round_trips(local_mode):
    """One call per registered tool, so a schema/serialization break in any of
    the nine shells surfaces here rather than in a client."""
    async with FastMCPClient(server.build_server()) as client:
        await client.call_tool("soma_write", {"text": "alpha"})
        assert _payload(await client.call_tool("soma_get", {"id": "note-ref-0001-0"}))["id"]
        debug = _payload(await client.call_tool("soma_debug", {"query": "alpha"}))
        assert debug["count_raw"] == 1
        context = _payload(await client.call_tool("soma_context",
                                                  {"question": "alpha", "deep": True}))
        assert context["context"].startswith(_DATA_BOUNDARY)
        updated = _payload(await client.call_tool(
            "soma_update", {"base_id": "note-ref-0001", "new_text": "beta"}))
        assert updated["status"] == "updated"
        feedback = _payload(await client.call_tool(
            "soma_feedback", {"question": "q", "verdict": "partially",
                              "causes": ["sources"], "source_ids": ["note-ref-0001-0"]}))
        assert feedback == {"status": "logged", "verdict": "⚠️ partially"}


async def test_fail_closed_over_the_protocol(monkeypatch):
    """No allowlist and no MCP_SINGLE_USER: tools answer with a readable denial."""
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")
    async with FastMCPClient(server.build_server()) as client:
        denied = _payload(await client.call_tool("soma_write", {"text": "x"}))
        assert denied["error"].startswith("no access to this instance")
        whoami = _payload(await client.call_tool("soma_whoami", {}))
        assert whoami["subject"] is None  # whoami stays reachable to debug the allowlist


async def test_unexpected_exceptions_are_masked(local_mode):
    class BrokenEngine(InMemoryEngine):
        def search(self, query: str) -> Any:
            raise RuntimeError("/srv/private/path leaked in a traceback")

    async with FastMCPClient(server.build_server(BrokenEngine())) as client:
        result = await client.call_tool("soma_search", {"query": "x"}, raise_on_error=False)
    assert result.is_error
    text = " ".join(getattr(block, "text", "") for block in result.content)
    assert "/srv/private/path" not in text
    assert "RuntimeError" not in text


@pytest.mark.parametrize(("mode", "protocol"), ERAS)
async def test_streamable_http_with_the_official_sdk_client(local_mode, serve_http,
                                                           mode, protocol):
    http = serve_http(server.build_server())
    async with SDKClient(http.url, mode=mode) as client:
        assert client.protocol_version == protocol
        assert client.server_info is not None
        assert client.server_info.version == soma_mcp.__version__
        listing = await client.list_tools()
        assert {tool.name for tool in listing.tools} == set(ANNOTATIONS)
        written = await client.call_tool("soma_write", {"text": "a note over http"})
        assert written.structured_content == {"status": "saved", "chunks": 1}

    # The wire carries the MCP camelCase names, whatever Python calls the fields.
    for hint in WIRE_HINTS:
        assert f'"{hint}"' in http.wire
    assert "read_only_hint" not in http.wire
    assert '"inputSchema"' in http.wire


def _wire_tools(bodies: list[bytes]) -> dict[str, dict[str, Any]]:
    """Pull the tools/list result out of the captured JSON (or SSE) bodies."""
    for body in bodies:
        text = body.decode("utf-8", errors="replace")
        for chunk in [text, *(line[len("data:"):] for line in text.splitlines()
                              if line.startswith("data:"))]:
            chunk = chunk.strip()
            if '"tools"' not in chunk or not chunk.startswith("{"):
                continue
            tools = (json.loads(chunk).get("result") or {}).get("tools")
            if tools:
                return {tool["name"]: tool for tool in tools}
    raise AssertionError("no tools/list result found on the wire")


async def test_wire_annotations_match_declared_hints(local_mode, serve_http):
    http = serve_http(server.build_server())
    async with SDKClient(http.url) as client:
        await client.list_tools()
    wire_tools = _wire_tools(http.bodies)
    for name, expected in ANNOTATIONS.items():
        hints = expected.model_dump(by_alias=True, exclude_none=True, mode="json")
        assert wire_tools[name]["annotations"] == hints


async def test_authenticated_subject_reaches_the_allowlist(monkeypatch, serve_http):
    """Bearer token -> token subject -> MCP_TOEGANG/SCHRIJF allowlists, end to end."""
    monkeypatch.setenv("MCP_TOEGANG_SUBJECTS", "auth0|owner,auth0|reader")
    monkeypatch.setenv("MCP_SCHRIJF_SUBJECTS", "auth0|owner")
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")
    verifier = StaticTokenVerifier(tokens={
        "owner-token": {"client_id": "c-owner", "scopes": ["mcp"], "sub": "auth0|owner"},
        "reader-token": {"client_id": "c-reader", "scopes": ["mcp"], "sub": "auth0|reader"},
        "stranger-token": {"client_id": "c-x", "scopes": ["mcp"], "sub": "auth0|stranger"},
    })
    monkeypatch.setattr(server, "_build_auth", lambda config: verifier)
    http = serve_http(server.build_server())

    async def call(token: str, tool: str, args: dict[str, Any]) -> Any:
        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"},
                                      timeout=httpx2.Timeout(30.0, read=300.0)) as http_client:
            transport = streamable_http_client(http.url, http_client=http_client)
            async with SDKClient(transport) as client:
                return (await client.call_tool(tool, args)).structured_content

    assert (await call("owner-token", "soma_whoami", {}))["subject"] == "auth0|owner"
    assert (await call("owner-token", "soma_write", {"text": "x"}))["status"] == "saved"
    assert (await call("reader-token", "soma_write", {"text": "x"}))["error"].startswith(
        "no write access")
    assert (await call("reader-token", "soma_get", {"id": "note-ref-0001-0"}))["id"]
    stranger = await call("stranger-token", "soma_search", {"query": "x"})
    assert stranger["result"][0]["error"].startswith("no access to this instance")

    # No token or a forged one never reaches a tool: the transport answers 401.
    async with httpx2.AsyncClient() as raw:
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert (await raw.post(http.url, json=request)).status_code == 401
        forged = await raw.post(http.url, json=request,
                                headers={"Authorization": "Bearer forged-token"})
        assert forged.status_code == 401


async def test_unauthenticated_transport_rejects_dns_rebinding(local_mode, serve_http):
    """The Host/Origin guard serve() applies to an unauthenticated server."""
    guard = {"host_origin_protection": server._host_origin_protection(authenticated=False)}
    http = serve_http(server.build_server(), **guard)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    async with httpx2.AsyncClient() as raw:
        rebound = await raw.post(http.url, json=request, headers={"Host": "evil.example:8000"})
        assert rebound.status_code == 421
        foreign = await raw.post(http.url, json=request,
                                 headers={"Origin": "http://evil.example"})
        assert foreign.status_code == 403
    async with SDKClient(http.url) as client:  # a local client still works
        assert len((await client.list_tools()).tools) == len(ANNOTATIONS)
