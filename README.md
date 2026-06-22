# SOMA MCP

**One private memory. Every agent you trust — powered by the official Model
Context Protocol.**

SOMA MCP is a **private, self-hosted reference implementation of the official
[Model Context Protocol](https://modelcontextprotocol.io) (MCP)**. It puts a
single person's memory behind a small set of MCP tools that any MCP-compatible
agent — Claude, ChatGPT, Cursor, VS Code, or your own — can call over an
authenticated connection.

Where most MCP servers wrap a public API or a shared SaaS backend, SOMA MCP wraps
**your own retrieval pipeline over your own data**, on hardware you control. Same
protocol, same clients, sovereign substrate.

> This repository is the **reference implementation** of the SOMA MCP server: the
> FastMCP transport shell, the FastMCP-free tool kernel, and the rate-limit /
> audit guard — with the retrieval engine abstracted behind an `Engine`
> interface. A dependency-free `InMemoryEngine` ships so the server runs and its
> tests pass out of the box. Plug in your own `Engine` to front your own memory.

[![spec](https://img.shields.io/badge/MCP_spec-2025--11--25-blue)](https://modelcontextprotocol.io)
[![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## Why it's different

| | Typical hosted MCP server | SOMA MCP |
|---|---|---|
| Backend | A public/SaaS API | *Your* retrieval pipeline over *your* data |
| Hosting | Vendor cloud | Self-hosted (you control the box and keys) |
| Tenancy | Often multi-tenant | One private memory per instance |
| Access | API key / shared auth | OAuth 2.1 **plus** a fail-closed subject allowlist |
| Data exposure | Provider sees your data | Data never leaves your infrastructure |
| Protocol | Official MCP | Official MCP (same clients, same wire) |

The differentiator is not the protocol — it's **sovereignty over the substrate**
while staying fully compatible with the standard.

## What it implements

- **Transport:** Streamable HTTP (the current MCP transport) at `/mcp`.
- **Capability:** `tools` — nine tools (search, get, debug, context, whoami,
  write, update, delete, feedback). A clean, valid subset of the protocol.
- **Authorization:** OAuth 2.1 via Auth0, **plus** a fail-closed subject
  allowlist (a valid token is necessary but not sufficient) and a stricter
  allowlist for writes.
- **Safety:** per-subject sliding-window rate limit, JSONL audit log on writes,
  a two-step confirm on delete, note size caps, masked internal errors, and a
  central **prompt-injection data-boundary fence** on every returned memory
  string.

See [`docs/compliance.md`](docs/compliance.md) for an honest gap analysis against
the spec, and [`docs/`](docs/) for architecture, security, tools, and auth.

## Quick start (local, unauthenticated)

```bash
pip install -e .
soma-mcp            # serves Streamable HTTP at http://localhost:8000/mcp
```

Without `AUTH0_*` env vars the server runs **unauthenticated** for local
experimentation (it warns loudly). Set `MCP_SINGLE_USER=1` so the fail-closed
guards allow your calls. Point [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
at `http://localhost:8000/mcp` to browse `tools/list` and fire calls.

Out of the box it uses the `InMemoryEngine` (substring search, in-memory notes) —
enough to see the protocol working end to end.

## Plug in your own memory

Implement the `Engine` protocol (`src/soma_mcp/engine.py`) over your own
retrieval stack and inject it:

```python
from soma_mcp import build_server
from my_stack import MyEngine          # implements soma_mcp.engine.Engine

mcp = build_server(MyEngine())
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

The `Engine` surface is exactly nine methods (search, filter, get, assemble
context, add/update/delete note, log feedback). The tool kernel, guards and
prompt-injection fence are reused unchanged.

## Production (authenticated)

Set the Auth0 variables and run behind TLS (e.g. a tunnel). See
[`docs/auth.md`](docs/auth.md) and [`.env.example`](.env.example).

| Variable | Purpose |
|---|---|
| `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `BASE_URL` | OAuth 2.1 provider. |
| `MCP_TOEGANG_SUBJECTS` | Comma-separated allowlist of subjects permitted to use the instance. |
| `MCP_SCHRIJF_SUBJECTS` | Allowlist of subjects permitted to write. |
| `MCP_SINGLE_USER` | `1` to run intentionally without an allowlist. Otherwise guards fail closed. |
| `MCP_RATE_LIMIT` | Calls per minute per subject (default `30`; `0` disables). |
| `MCP_JWT_SIGNING_KEY`, `MCP_STORAGE_ENCRYPTION_KEY` | Enable encrypted, persistent token storage (`pip install -e .[auth]`). |
| `SOMA_DATA` | Data path (token store, audit log). |

## Tests

```bash
pip install -e .[dev]
pytest
```

The security-critical kernel (fail-closed guards, the data-boundary fence, the
two-step delete, size caps) is covered without an auth environment — the shell is
dumb, the kernel is covered.

## Note on language

SOMA is a Dutch-language personal system. The **live** SOMA server uses Dutch
tool parameter names (`vraag`, `tekst`, `bevestig`, `diep`, `oordeel`), as
documented under [`docs/`](docs/). This public reference **anglicizes** them
(`question`, `text`, `confirm`, `deep`, `verdict`) for accessibility; the
semantics are identical. A couple of result-dict keys retain their Dutch names
(`tekst`, `bronnen`, `datum`, `herkomst`) to match the documented surface.

## About the standard

MCP is an open standard introduced by Anthropic in 2024. In December 2025 it was
contributed to the **Agentic AI Foundation (AAIF)** under the **Linux
Foundation**, placing it under vendor-neutral governance. This implementation
tracks the **2025-11-25** stable specification revision.

- Specification & SDKs: <https://github.com/modelcontextprotocol>
- Site: <https://modelcontextprotocol.io>

## License

[Apache-2.0](LICENSE).
