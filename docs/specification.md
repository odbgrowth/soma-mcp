# SOMA MCP — Implementation Specification

This document describes SOMA MCP's concrete protocol surface and how it maps onto
the official Model Context Protocol (revision **2025-11-25**). For the gap
analysis, see [`compliance.md`](compliance.md); for tool details, see
[`tools.md`](tools.md).

## 1. Stack

| Layer | Choice |
|---|---|
| Protocol | Model Context Protocol, JSON-RPC 2.0 |
| Framework | [FastMCP](https://github.com/jlowin/fastmcp) `>=3.4.2` on `mcp >=1.27.2` |
| Transport | Streamable HTTP, served at `/mcp` on port `8000` |
| Authorization | OAuth 2.1 via `Auth0Provider` |
| Server name | `SOMA` |
| Capabilities advertised | `tools` |

The protocol machinery (framing, handshake, negotiation, tool discovery, auth
metadata) is provided by FastMCP / the `mcp` SDK. SOMA's own code is the thin
transport shell (`soma_mcp.py`) plus the tool kernel (`soma_mcp_kern.py`).

## 2. Transport

SOMA serves **Streamable HTTP**:

```python
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

- Endpoint path: `/mcp`.
- Production base URL: behind a Cloudflare Tunnel, e.g.
  `https://soma.usesiva.net/mcp`. TLS terminates at the tunnel; the container
  port is not publicly exposed.
- This is the current transport (it superseded HTTP+SSE in the 2025-03-26
  revision). stdio is intentionally not offered — SOMA is a long-running
  networked server, not a subprocess.

## 3. Lifecycle

The `initialize` handshake is performed by the SDK. The client sends its
supported `protocolVersion`, its `capabilities` and `clientInfo`; SOMA responds
with the negotiated `protocolVersion`, its server `capabilities` (`tools`) and
`serverInfo` (name `SOMA`). After `initialized`, the client may call
`tools/list` and `tools/call`.

SOMA does not override the handshake. The one startup behaviour worth noting is a
**cold-start mitigation**: before serving, the server warms the embedding model
(`soma_core.zoek("warmup")`) so the first real query is fast. Warmup failure is
non-fatal — the server still serves and falls back to lazy loading.

## 4. Capabilities

SOMA advertises exactly one server capability: **`tools`**. It does not advertise
`resources`, `prompts`, `completions` or client-streamed `logging`. All are
optional in the spec; see [`compliance.md`](compliance.md) §3 for the rationale
and roadmap.

## 5. Tools surface

Nine tools, registered with `@mcp.tool` in `soma_mcp.py`. Input schemas are
derived from the Python signatures; descriptions are the docstrings the client
sees.

| Tool | Kind | Signature (summary) |
|---|---|---|
| `soma_search` | read | `(query: str, limit: int = 15) -> list[dict]` |
| `soma_get` | read | `(id: str) -> dict` |
| `soma_debug` | read (diagnostic) | `(query: str, limit: int = 25) -> dict` |
| `soma_context` | read (full pipeline) | `(vraag: str, max_tekens: int = 30000, diep: bool = False) -> dict` |
| `soma_whoami` | read (identity) | `() -> dict` |
| `soma_write` | write | `(tekst: str) -> dict` |
| `soma_update` | write | `(basis_id: str, nieuwe_tekst: str) -> dict` |
| `soma_delete` | write (guarded) | `(basis_id: str, bevestig: bool = False) -> dict` |
| `soma_feedback` | write (log) | `(vraag, oordeel, antwoord?, opmerking?, oorzaken?, bron_ids?) -> dict` |

Full per-tool reference: [`tools.md`](tools.md).

## 6. Result and error conventions

- **Results are JSON-serializable** dicts or lists of dicts (structured content).
- **Returned text from memory is fenced.** Every memory string the server hands
  back is prefixed with an explicit data-boundary marker telling the calling
  model the content is *data, not instructions* — a centralized prompt-injection
  defense in the kernel (`_omhein`). See [`security.md`](security.md).
- **Errors are data, not exceptions.** Access denial, rate-limit, and validation
  failures are returned as a result dict carrying a `fout` (error) field, so the
  calling model can read the reason and react. This is a deliberate variant of
  raising protocol errors.
- **Internal errors are masked.** `FastMCP(..., mask_error_details=True)` ensures
  unexpected exceptions return a generic message instead of a traceback that
  could leak paths, queries or memory fragments. Explicit `ToolError` messages
  still pass through.

## 7. Authorization model (summary)

OAuth 2.1 via Auth0 establishes *who* is calling (the token `subject`). SOMA then
applies its own allowlist guards on top of every call:

- Read/general access requires the subject to be in `MCP_TOEGANG_SUBJECTS`.
- Write tools additionally require `MCP_SCHRIJF_SUBJECTS`.
- **Fail-closed:** if the allowlist is unset and `MCP_SINGLE_USER != 1`, all
  access is denied.
- A per-subject sliding-window rate limit (`MCP_RATE_LIMIT`, default 30/min)
  applies to every tool.

Details: [`auth.md`](auth.md).

## 8. Configuration reference

| Variable | Purpose |
|---|---|
| `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE` | Auth0 OAuth provider configuration. |
| `BASE_URL` | Public base URL used in OAuth metadata/redirects. |
| `MCP_TOEGANG_SUBJECTS` | Comma-separated allowlist of subjects permitted to use the instance. |
| `MCP_SCHRIJF_SUBJECTS` | Comma-separated allowlist of subjects permitted to write. |
| `MCP_SINGLE_USER` | `1` to run intentionally without an allowlist (single-user). Otherwise guards fail closed. |
| `MCP_RATE_LIMIT` | Calls per minute per subject (default `30`; `0` disables). |
| `MCP_JWT_SIGNING_KEY`, `MCP_STORAGE_ENCRYPTION_KEY` | Enable Fernet-encrypted persistent token storage (no reconnect after rebuilds). |
| `SOMA_DATA` | Data volume path (token store, audit log). |

## 9. Versioning

SOMA tracks the official spec revision negotiated by the SDK (currently
2025-11-25). Pinning an explicit `serverInfo.version` and documenting the
supported revision range are tracked roadmap items in
[`compliance.md`](compliance.md) §6.
