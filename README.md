# SOMA MCP

**One private memory. Every agent you trust, through the official Model Context
Protocol.**

[![CI](https://github.com/odbgrowth/soma-mcp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/odbgrowth/soma-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![MCP protocol](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![Release](https://img.shields.io/github/v/release/odbgrowth/soma-mcp?sort=semver)](https://github.com/odbgrowth/soma-mcp/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

## What it is

SOMA MCP is a **private, self-hosted reference implementation of an
[MCP](https://modelcontextprotocol.io) server** that puts one person's memory
behind nine MCP tools. Claude, ChatGPT, Cursor, VS Code or your own agent can
search, read, write, correct and audit that memory over an authenticated
connection, with the same protocol and the same clients as any other MCP server.

This repository contains the transport shell (FastMCP), the FastMCP-free tool
kernel with its security guards, and an `Engine` interface for the retrieval
backend. A dependency-free `InMemoryEngine` ships so the server runs and its
tests pass out of the box; plug in your own `Engine` to front your own memory.

## What it is not

- **Not a hosted service.** You run it, on hardware and keys you control.
- **Not multi-tenant.** One instance is one person's memory.
- **Not an open endpoint.** A valid OAuth token is necessary but not sufficient:
  the token's subject must also be on a fail-closed allowlist.
- **Not a retrieval engine.** The bundled `InMemoryEngine` does substring search
  for demos and tests. Real retrieval is your `Engine`.
- **Not a fork of MCP.** It is built on the official MCP Python SDK through
  FastMCP and speaks the standard wire protocol.

## Why self-hosted memory

Agents get more useful as they remember more, and what they remember about you
is among the most sensitive data you have. Most MCP servers wrap a vendor API;
SOMA MCP wraps **your own retrieval pipeline over your own data**. The protocol
is shared with the whole ecosystem; the substrate stays yours.

| | Typical hosted MCP server | SOMA MCP |
|---|---|---|
| Backend | A public or SaaS API | Your retrieval pipeline over your data |
| Hosting | Vendor cloud | Self-hosted |
| Tenancy | Often multi-tenant | One private memory per instance |
| Access | API key or shared auth | OAuth 2.1 plus a fail-closed subject allowlist |
| Protocol | Official MCP | Official MCP (same clients, same wire) |

## Supported stack

| Component | Version |
|---|---|
| SOMA MCP | `0.2.0` ([changelog](CHANGELOG.md)) |
| FastMCP | `>=4.1,<5` ([PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp)) |
| MCP Python SDK | `>=2.3,<3` ([modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)) |
| MCP protocol | **2026-07-28**, plus the handshake revisions 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25, negotiated per request by the SDK |
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| Transport | Streamable HTTP at `/mcp` |

`soma-mcp --version` prints the exact versions installed. What is tested and
what is delegated to the SDK is listed in [`docs/compliance.md`](docs/compliance.md).

## Quick start (local, unauthenticated)

```bash
git clone https://github.com/odbgrowth/soma-mcp.git
cd soma-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .

export MCP_SINGLE_USER=1   # deliberate single-user mode; otherwise every call is denied
soma-mcp                   # Streamable HTTP at http://127.0.0.1:8000/mcp
```

Without the `AUTH0_*` variables the server runs **unauthenticated**, says so in
its log, listens on `127.0.0.1` only and rejects requests whose `Host` or
`Origin` is not local (DNS-rebinding protection). That is for experiments on
your own machine, never for a network.

List and call the tools with the official
[MCP Inspector](https://github.com/modelcontextprotocol/inspector) (Node 22.19+):

```bash
npx @modelcontextprotocol/inspector --server-url http://127.0.0.1:8000/mcp --transport http
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --transport http \
  --protocol-era modern --method tools/call --tool-name soma_whoami
```

or from Python with the MCP SDK client:

```python
import anyio
from mcp import Client


async def main() -> None:
    async with Client("http://127.0.0.1:8000/mcp") as client:
        print(client.protocol_version)  # 2026-07-28
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])


anyio.run(main)
```

More clients and payloads: [`docs/examples.md`](docs/examples.md).

## Plug in your own memory

Implement the `Engine` protocol ([`src/soma_mcp/engine.py`](src/soma_mcp/engine.py))
over your own retrieval stack and inject it:

```python
from my_stack import MyEngine  # your implementation of soma_mcp.Engine

from soma_mcp import build_server

mcp = build_server(MyEngine())
mcp.run(transport="http", host="127.0.0.1", port=8000)
```

The `Engine` surface is nine methods (search, filter, get, assemble context,
add/update/delete note, full note, log feedback). The tool kernel, guards and
prompt-injection fence are reused unchanged. Prefer `soma-mcp` for serving: it
applies the bind-address and DNS-rebinding defaults described above.

## Production (authenticated)

Configure Auth0 and run behind a TLS-terminating proxy. All five Auth0 settings
are required together; a partial configuration refuses to start instead of
running unauthenticated. Details: [`docs/auth.md`](docs/auth.md),
[`.env.example`](.env.example).

| Variable | Purpose |
|---|---|
| `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `BASE_URL` | OAuth 2.1 through Auth0. All or none. |
| `MCP_TOEGANG_SUBJECTS` | Comma-separated allowlist of token subjects that may use the instance. |
| `MCP_SCHRIJF_SUBJECTS` | Allowlist of subjects that may write, update and delete. |
| `MCP_SINGLE_USER` | `1` to run deliberately without an allowlist. Otherwise the guards fail closed. |
| `MCP_RATE_LIMIT` | Calls per minute per subject (default `30`; `0` disables). |
| `MCP_JWT_SIGNING_KEY`, `MCP_STORAGE_ENCRYPTION_KEY` | Both or neither: encrypted OAuth state on the data volume, so connectors survive restarts (`pip install ".[auth]"`). |
| `MCP_HOST`, `MCP_PORT` | Bind address. Default `0.0.0.0:8000` with Auth0, `127.0.0.1:8000` without. |
| `SOMA_DATA` | Data directory for the token store (`mcp_oauth/`) and the audit log. |

## Security model

- **Two keys:** an OAuth 2.1 token *and* an allowlisted subject; a stricter
  allowlist for writes. Fail closed when an allowlist is missing.
- **Fail-closed configuration:** partial Auth0 or token-storage settings stop the
  server at startup.
- **Encrypted token storage:** Fernet-encrypted `FileTreeStore` with sanitized
  keys (0.1.x used the pickle-based `DiskStore`, CVE-2025-69872).
- **Prompt-injection fence:** every memory string is returned marked as data,
  not instructions.
- **Safety valves:** per-subject rate limit, JSONL audit log of writes, two-step
  delete, size caps, masked internal errors.

Threat model: [`docs/security.md`](docs/security.md). Reporting vulnerabilities:
[`SECURITY.md`](SECURITY.md).

## Public Python API

Supported imports: `soma_mcp.Engine`, `soma_mcp.InMemoryEngine`,
`soma_mcp.Kernel`, `soma_mcp.build_server`, `soma_mcp.main` and
`soma_mcp.__version__`. `soma_mcp.config.ConfigurationError` is what
`build_server` raises on a partial configuration. Everything else is internal
and may change in a minor release.

## Development

```bash
pip install -e ".[dev,auth]"
.devflows/verify            # ruff, mypy, pytest with coverage, release metadata, whitespace
.devflows/run.py package    # build sdist and wheel, twine check
```

CI runs the same gates on Python 3.10 to 3.14, the declared dependency floors,
pip-audit, gitleaks, a clean-wheel smoke test and the applicable scenarios of
the official MCP conformance suite. Releases are tag-driven and documented in
[`RELEASE.md`](RELEASE.md); upgrade notes live in
[`docs/upgrading.md`](docs/upgrading.md). Contributor and agent rules:
[`AGENTS.md`](AGENTS.md).

## Documentation

[`docs/README.md`](docs/README.md) is the map: architecture, specification,
tools, auth, security, compliance, examples, upgrading and the architecture
decision records.

## Note on language

SOMA is a Dutch-language personal system. The private production server uses
Dutch tool parameter names (`vraag`, `tekst`, `bevestig`, `diep`, `oordeel`);
this public reference uses English ones (`question`, `text`, `confirm`, `deep`,
`verdict`) with identical semantics. Some result keys keep their Dutch names
(`tekst`, `bronnen`, `datum`, `herkomst`), as do the allowlist variables
(`MCP_TOEGANG_SUBJECTS` = access, `MCP_SCHRIJF_SUBJECTS` = write).

## About the standard

MCP is an open standard introduced by Anthropic in November 2024 and, since
December 2025, governed by the Agentic AI Foundation under the Linux Foundation.
SOMA MCP targets the **2026-07-28** revision.

- Specification: <https://modelcontextprotocol.io/specification/2026-07-28>
- SDKs and tools: <https://github.com/modelcontextprotocol>

## License

[Apache-2.0](LICENSE).
