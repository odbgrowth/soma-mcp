# SOMA MCP

**One private memory. Every agent you trust — powered by the official Model Context Protocol.**

SOMA MCP is a **private, self-hosted implementation of the official
[Model Context Protocol](https://modelcontextprotocol.io) (MCP)**. It exposes a
single person's memory — AI conversations (Claude, ChatGPT), manual notes,
health data (WHOOP), listening history (Spotify) and uploaded documents — as a
small set of MCP tools that any MCP-compatible agent can call over an
authenticated connection.

Where most MCP servers wrap a public API or a shared SaaS backend, SOMA MCP
wraps **your own retrieval pipeline over your own data**, running on hardware you
control. Same protocol, same clients, sovereign substrate.

---

## What this is, in one paragraph

SOMA MCP is the [FastMCP](https://github.com/jlowin/fastmcp)-based transport
shell (`soma_mcp.py`) in front of SOMA's retrieval engine. It speaks **JSON-RPC
2.0 over Streamable HTTP**, authenticates clients with **OAuth 2.1** (via Auth0),
and advertises the **`tools`** capability — nine tools that search, read, write,
correct and audit a personal memory. It is the only interface the owner actually
uses day to day; the Streamlit UI shares the exact same pipeline underneath.

## Quick start

You need an MCP-compatible client (Claude, ChatGPT, Cursor, VS Code, or a custom
agent using an MCP SDK) and the connection URL for a running SOMA instance.

1. **Point your client at the server.** SOMA serves MCP at the `/mcp` path of its
   base URL — in production behind a Cloudflare Tunnel, e.g.
   `https://soma.usesiva.net/mcp`.
2. **Authenticate.** The first connection triggers the OAuth 2.1 flow: your
   client is redirected to Auth0, you sign in, and the client receives a scoped
   access token. Tokens are persistent across server rebuilds, so you connect
   once. See [`auth.md`](auth.md).
3. **Discover tools.** Your client calls `tools/list` and sees the nine SOMA
   tools with their schemas and descriptions. See [`tools.md`](tools.md).
4. **Call a tool.** Ask your agent a question; it calls `soma_context` or
   `soma_search` and answers from your memory. See [`examples.md`](examples.md).

Running the server itself (containers, tunnel, env vars) is covered in the
top-level [`README.md`](../README.md) and [`architecture.md`](architecture.md).

## Documentation map

| Document | What it covers |
|----------|----------------|
| [`positioning.md`](positioning.md) | What SOMA MCP is, who it's for, and how it differs from a hosted MCP server. |
| [`compliance.md`](compliance.md) | Honest gap analysis against the official MCP specification — what's compliant, what's a deliberate subset, what's roadmap. |
| [`specification.md`](specification.md) | SOMA's concrete protocol surface: transport, lifecycle, capabilities, message shapes. |
| [`architecture.md`](architecture.md) | How the server is built — the shell/kernel split, the shared pipeline, deployment topology. |
| [`security.md`](security.md) | The self-hosted threat model: fail-closed access, rate limiting, audit logging, prompt-injection data-fencing. |
| [`tools.md`](tools.md) | Reference for all nine tools — inputs, outputs, guards, when to use each. |
| [`auth.md`](auth.md) | OAuth 2.1 flow, subjects, scoped access (read vs write), token persistence. |
| [`examples.md`](examples.md) | Connecting from Claude, ChatGPT and a custom SDK agent, with sample calls. |

## Standard, and where it lives now

MCP is an open standard, introduced by Anthropic in November 2024. In December
2025 it was contributed to the **Agentic AI Foundation (AAIF)** under the **Linux
Foundation**, alongside A2A, goose and AGENTS.md, placing it under vendor-neutral
governance. SOMA MCP tracks the **2025-11-25** stable specification revision; the
next revision (release candidate **2026-07-28**) is in draft.

- Official site: <https://modelcontextprotocol.io>
- Specification & SDKs: <https://github.com/modelcontextprotocol>

SOMA MCP's goal is to be a recognizable, compatible citizen of that ecosystem —
while keeping your memory entirely your own.
