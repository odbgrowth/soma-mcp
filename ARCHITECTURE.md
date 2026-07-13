# Architecture

This repository is the public Python reference implementation of a self-hosted SOMA MCP
server. The package exposes MCP tools from `src/soma_mcp`, with optional persistent OAuth
support and tests under `tests/`.

It is an integration boundary, not the owner of a user's memory. Protocol adapters must
preserve self-ownership, revocable access, evidence provenance, and provider neutrality.
Secrets and runtime token stores never belong in Git.
