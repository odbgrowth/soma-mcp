# Positioning

> **SOMA MCP** — a private, self-hosted implementation of the official Model
> Context Protocol.
>
> **Tagline:** *One private memory. Every agent you trust — powered by the
> official MCP standard.*

## The one-sentence version

SOMA MCP gives you a single, sovereign memory that any MCP-compatible agent can
read from and write to — running on your hardware, under your keys, speaking the
same protocol as the rest of the ecosystem.

## What it is

SOMA MCP is the Model Context Protocol surface of **SOMA**, a personal
memory / RAG system. SOMA ingests your AI conversations (Claude, ChatGPT),
manual notes, health data (WHOOP), listening history (Spotify) and documents,
embeds them, and answers questions over them. SOMA MCP exposes that engine as
**nine MCP tools** so the memory is reachable directly from inside your agents —
not just from SOMA's own UI.

It is a **compatible, private implementation** of the official standard. The
protocol is the public one; the data and the deployment are entirely yours.

## What it is *not*

- It is **not a fork of the protocol.** It tracks the official MCP spec
  (currently 2025-11-25) and is built on the reference Python stack (FastMCP /
  `mcp`).
- It is **not a multi-tenant SaaS memory.** Each instance is one person's memory.
  Multi-tenancy, where it exists, is instance-per-user, not shared storage.
- It is **not a public, open endpoint.** Access is fail-closed: a token alone is
  not enough; the subject must be on an allowlist.

## Who it's for

- People who already run an MCP client (Claude, ChatGPT, Cursor, VS Code, custom
  agents) and want those agents to share **one** durable memory instead of
  re-explaining context every session.
- People who want that memory **self-hosted** — on a NUC, a homelab box, a
  private VPS — rather than handed to a third party.
- Builders who want a worked example of a non-trivial, authenticated, single-
  capability MCP server.

## How it's different from a typical MCP server

| | Typical hosted MCP server | SOMA MCP |
|---|---|---|
| Backend | A public/SaaS API | *Your* retrieval pipeline over *your* data |
| Hosting | Vendor cloud | Self-hosted (you control the box and keys) |
| Tenancy | Often multi-tenant | One private memory per instance |
| Access | API key / shared auth | OAuth 2.1 **plus** a fail-closed subject allowlist |
| Data exposure | Provider sees your data | Data never leaves your infrastructure |
| Protocol | Official MCP | Official MCP (same clients, same wire) |

The differentiator is not the protocol — it is **sovereignty over the substrate**
while staying fully compatible with the standard.

## Naming

- **Product name:** SOMA MCP (long form: *SOMA Private MCP Server*).
- **Server identity on the wire:** `SOMA` (the `serverInfo.name`).

## Messaging building blocks

- *"A private, self-hosted implementation of the official Model Context
  Protocol."*
- *"Same protocol as Claude and ChatGPT use — your memory, your hardware, your
  keys."*
- *"Sovereign by design, compatible by default."*

## Relationship to SIVA

SOMA is also the foundation under **SIVA** (the product/multi-user layer) and the
later SNA retention layer. SOMA MCP is the protocol-standard doorway into that
foundation: when SIVA onboards a user, it provisions a SOMA instance, and SOMA
MCP is how trusted agents reach it.
