# SOMA MCP implementation specification

SOMA MCP's concrete protocol surface and how it maps onto the official Model
Context Protocol, revision **2026-07-28**. Gap analysis and test evidence:
[`compliance.md`](compliance.md). Tool reference: [`tools.md`](tools.md).

## 1. Stack

| Layer | Choice |
|---|---|
| Protocol | MCP **2026-07-28**; handshake revisions 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 for older clients |
| Framing | JSON-RPC 2.0 |
| Framework | [FastMCP](https://github.com/PrefectHQ/fastmcp) `>=4.1,<5` on the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) `>=2.3,<3` |
| Transport | Streamable HTTP at `/mcp`, default port `8000` |
| Authorization | OAuth 2.1 through Auth0 (`Auth0Provider`), optional for local use |
| Server identity | `serverInfo.name` = `SOMA`, `serverInfo.version` = `soma_mcp.__version__` |
| Capabilities | `tools` |

The protocol machinery (framing, era negotiation, discovery, schemas,
validation, OAuth metadata) is provided by FastMCP and the SDK. SOMA's code is
the transport shell (`server.py`), its configuration (`config.py`) and the tool
kernel (`kernel.py`).

## 2. Transport

```bash
soma-mcp    # soma_mcp.serve(): build_server() + mcp.run(transport="http", ...)
```

- Endpoint: `/mcp`. Behind a TLS-terminating proxy in production:
  `https://<your-host>/mcp`.
- Bind address: `MCP_HOST`/`MCP_PORT`; default `0.0.0.0:8000` with Auth0 and
  `127.0.0.1:8000` without. The unauthenticated server validates `Host` and
  `Origin` strictly against DNS rebinding; with Auth0 the guard follows
  FastMCP's `FASTMCP_HTTP_HOST_ORIGIN_PROTECTION` setting (off by default).
- Streamable HTTP is the current MCP transport. stdio is not offered: SOMA is a
  long-running networked server, not a subprocess of one client.

## 3. Protocol eras and lifecycle

The SDK routes every request by its `MCP-Protocol-Version` header, so both eras
share one endpoint and SOMA has no era-specific code.

**2026-07-28 (modern, sessionless).** The client may call `server/discover`,
which returns the supported versions, the `tools` capability, the server
instructions and the server identity. Every request carries
`io.modelcontextprotocol/protocolVersion` and the client capabilities in `_meta`;
every result carries `io.modelcontextprotocol/serverInfo` in its `_meta`. There
is no `initialize`, no `ping` and no `Mcp-Session-Id`.

**Handshake era (2024-11-05 to 2025-11-25).** The client sends `initialize`; the
server answers with the negotiated `protocolVersion`, `capabilities`,
`serverInfo` and `instructions`, and mints an `Mcp-Session-Id`. After
`notifications/initialized` the client calls `tools/list` and `tools/call`.

SOMA's tools need no client capability (no sampling, elicitation or roots), so
they behave identically in both eras. The FastMCP client and the MCP SDK
`Client` negotiate the modern era by default; `mode="legacy"` forces the
handshake.

## 4. Capabilities

SOMA's surface is **tools**: nine tools, listed by `tools/list`. FastMCP 4.1
also advertises its framework defaults, which SOMA leaves empty or unused:

| Capability | 2026-07-28 (`server/discover`) | Handshake era (`initialize`) | Content |
|---|---|---|---|
| `tools` | `listChanged: false` | `listChanged: true` | the nine SOMA tools |
| `prompts` | `listChanged: false` | `listChanged: true` | none (`prompts/list` is empty) |
| `resources` | `subscribe: false`, `listChanged: false` | `subscribe: false`, `listChanged: true` | none (`resources/list` is empty) |
| `logging` | `{}` | `{}` | FastMCP's log notifications; SOMA sends none |
| `extensions` | `io.modelcontextprotocol/ui` | not applicable | FastMCP default; SOMA ships no UI |

The tool set never changes at runtime, so no list-changed notification is sent.
`completions` is not advertised. `tests/test_transport.py` pins this table, so a
FastMCP upgrade that changes it fails CI. See [`compliance.md`](compliance.md) §3.

## 5. Tool surface

Nine tools, registered with `@mcp.tool` in `server.py`. Input schemas come from
the Python signatures; descriptions are the docstrings; annotations come from
`instructions.ANNOTATIONS`.

| Tool | Kind | Signature |
|---|---|---|
| `soma_search` | read | `(query: str, limit: int = 15) -> list[dict]` |
| `soma_get` | read | `(id: str) -> dict` |
| `soma_debug` | read (diagnostic) | `(query: str, limit: int = 25) -> dict` |
| `soma_context` | read (full pipeline) | `(question: str, max_tokens: int = 30000, deep: bool = False) -> dict` |
| `soma_whoami` | identity | `() -> dict` |
| `soma_write` | write | `(text: str) -> dict` |
| `soma_update` | write (destructive) | `(base_id: str, new_text: str) -> dict` |
| `soma_delete` | write (destructive, two-step) | `(base_id: str, confirm: bool = False) -> dict` |
| `soma_feedback` | write (log, not memory) | `(question: str, verdict: str, answer: str = "", comment: str = "", causes: list[str] \| None = None, source_ids: list[str] \| None = None) -> dict` |

Annotations travel with `tools/list` under the MCP wire names `readOnlyHint`,
`destructiveHint`, `idempotentHint` and `openWorldHint` (Python code uses the
SDK's snake_case attributes). A transport test asserts the wire form.

## 6. Results and errors

- **Structured results.** Every tool returns a JSON object (a list result is
  wrapped by FastMCP as `{"result": [...]}`) in `structuredContent`, with the
  same JSON as text content.
- **Fenced memory text.** Every memory text a tool returns carries a
  data-boundary prefix marking it as data, not instructions; metadata labels do
  not. See [`security.md`](security.md) §6.
- **Denials are data.** Access, rate-limit and validation failures are ordinary
  results with an `error` field (`isError` stays false), so the calling model
  can read the reason and react.
- **Unexpected exceptions are masked.** `mask_error_details=True` returns a
  generic message with `isError: true`; no traceback reaches the client.
  Protocol-level failures (unknown method, invalid parameters, unsupported
  protocol version) are standard JSON-RPC errors produced by the SDK.

## 7. Authorization model (summary)

OAuth 2.1 establishes who is calling (the token subject). The kernel then
applies:

- `MCP_TOEGANG_SUBJECTS` for every tool except `soma_whoami`;
- `MCP_SCHRIJF_SUBJECTS` additionally for the write tools;
- fail closed when an allowlist is missing, unless `MCP_SINGLE_USER=1`;
- a per-subject sliding-window rate limit (`MCP_RATE_LIMIT`, default 30/min).

Details: [`auth.md`](auth.md).

## 8. Configuration reference

| Variable | Purpose |
|---|---|
| `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `BASE_URL` | Auth0 OAuth configuration. All or none; partial sets refuse to start. |
| `MCP_TOEGANG_SUBJECTS` | Comma-separated subjects allowed to use the instance. |
| `MCP_SCHRIJF_SUBJECTS` | Comma-separated subjects allowed to write. |
| `MCP_SINGLE_USER` | `1` to run deliberately without an allowlist (with Auth0 this admits every account the tenant can sign in; the server warns). |
| `MCP_RATE_LIMIT` | Calls per minute per subject (default `30`; `0` disables). |
| `MCP_JWT_SIGNING_KEY`, `MCP_STORAGE_ENCRYPTION_KEY` | Both or neither: encrypted, persistent OAuth state in `$SOMA_DATA/mcp_oauth/`. |
| `MCP_HOST`, `MCP_PORT` | Bind address; defaults depend on whether Auth0 is configured. |
| `SOMA_DATA` | Data directory (token store, audit log). Defaults to the working directory. |

## 9. Versioning

- **SOMA MCP version:** `soma_mcp.__version__` is the single source. It is the
  package version, `serverInfo.version`, the version in `soma-mcp --version`,
  and the release tag `v{version}`.
- **Protocol revision:** negotiated per request by the MCP SDK. `soma-mcp
  --version` prints the revisions the installed SDK serves.
- **Framework ranges:** in `pyproject.toml`, bounded below the next major.

Release process: [`RELEASE.md`](../RELEASE.md).
