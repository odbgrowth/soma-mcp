# SOMA MCP documentation

SOMA MCP is a private, self-hosted reference implementation of an
[MCP](https://modelcontextprotocol.io) server. It exposes one person's memory
(notes, imported conversations, documents, whatever your `Engine` indexes) as
nine MCP tools that any MCP client can call over an authenticated connection.

## In one paragraph

A [FastMCP](https://github.com/PrefectHQ/fastmcp) transport shell
(`src/soma_mcp/server.py`) sits in front of a FastMCP-free tool kernel
(`src/soma_mcp/kernel.py`) and an injected retrieval `Engine`
(`src/soma_mcp/engine.py`). It speaks JSON-RPC 2.0 over Streamable HTTP at
`/mcp`, implements MCP revision **2026-07-28** (and the older handshake
revisions through the MCP Python SDK), authenticates clients with OAuth 2.1
through Auth0, and exposes its memory through tools only (no prompts or
resources).

## Using a running instance

You need an MCP client (Claude, ChatGPT, Cursor, VS Code, the MCP Inspector or
your own agent on an MCP SDK) and the instance URL, `https://<your-host>/mcp`.

1. **Add the server** to your client with that URL.
2. **Authenticate.** The first request starts the OAuth 2.1 flow: sign in at the
   instance's Auth0 tenant and the client receives a token. See [`auth.md`](auth.md).
3. **Get allowlisted.** Call `soma_whoami`, give the subject to the instance
   owner, who adds it to `MCP_TOEGANG_SUBJECTS` (and `MCP_SCHRIJF_SUBJECTS` for
   writes).
4. **Ask.** The agent picks `soma_context` or `soma_search` and answers from the
   returned memory. See [`tools.md`](tools.md) and [`examples.md`](examples.md).

Running the server yourself: the top-level [`README.md`](../README.md).

## Documentation map

| Document | What it covers |
|---|---|
| [`positioning.md`](positioning.md) | What SOMA MCP is, who it is for, how it differs from a hosted MCP server. |
| [`specification.md`](specification.md) | The concrete protocol surface: stack, transport, protocol eras, capabilities, configuration. |
| [`compliance.md`](compliance.md) | What is implemented, tested, delegated to the SDK, deliberately left out, or roadmap. |
| [`architecture.md`](architecture.md) | Shell / kernel / engine split, guards, deployment shape, release versus deployment. |
| [`tools.md`](tools.md) | All nine tools: parameters, results, guards, annotations, when to use each. |
| [`auth.md`](auth.md) | OAuth 2.1 through Auth0, subjects, read and write allowlists, token storage. |
| [`security.md`](security.md) | Threat model and the controls that implement it, operator checklist. |
| [`examples.md`](examples.md) | Connecting from Claude, ChatGPT, editors, the Inspector and the Python SDK. |
| [`upgrading.md`](upgrading.md) | Upgrade notes per release, starting with 0.1.x → 0.2.0. |
| [`../RELEASE.md`](../RELEASE.md) | How a version is tagged, built, attested and released. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | What changed in each release. |
| [`adr/`](adr/) | Architecture decision records ([ADR-003](adr/003-mcp-sdk-v2-fastmcp4-upgrade.md): MCP SDK v2, FastMCP 4, 2026-07-28). |
| [`agent-roles.md`](agent-roles.md), [`agent-knowledge.md`](agent-knowledge.md) | Rules and accumulated knowledge for the coding agents that work on this repository. |

## The standard

MCP is an open standard introduced by Anthropic in November 2024. In December
2025 it was contributed to the Agentic AI Foundation (AAIF) under the Linux
Foundation, alongside A2A, goose and AGENTS.md. The current revision is
**2026-07-28**, which SOMA MCP implements.

- Specification: <https://modelcontextprotocol.io/specification/2026-07-28>
- SDKs and tools: <https://github.com/modelcontextprotocol>
