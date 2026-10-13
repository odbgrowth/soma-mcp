# Architecture

This repository is the public Python reference implementation of a self-hosted
SOMA MCP server: a FastMCP 4 transport shell (`src/soma_mcp/server.py`) on the
MCP Python SDK v2, a FastMCP-free configuration module (`config.py`) and tool
kernel (`kernel.py`, `guard.py`), and an injected retrieval `Engine`
(`engine.py`). It serves MCP revision 2026-07-28 and the older handshake
revisions over Streamable HTTP, with optional Auth0 OAuth and encrypted,
persistent token storage. Tests live under `tests/`; details in
`docs/architecture.md`.

It is an integration boundary, not the owner of a user's memory. Protocol adapters must
preserve self-ownership, revocable access, evidence provenance, and provider neutrality.
Secrets and runtime token stores never belong in Git.
