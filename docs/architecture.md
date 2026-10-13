# Architecture

How SOMA MCP is built. The guiding principle is a **private instance**: one
person's memory, one deployment, one set of keys.

## 1. Shell, kernel, engine

```text
                 MCP client (Claude, ChatGPT, IDE, SDK agent)
                                   │  JSON-RPC 2.0, Streamable HTTP, /mcp
                                   ▼
   server.py   FastMCP shell: protocol eras, OAuth (Auth0), token subject,
               tool registration, error masking, bind and DNS-rebinding defaults
                                   │  subject + validated arguments
                                   ▼
   kernel.py   tool logic: rate limit, allowlists, validation, prompt-injection
               fence, two-step delete, audit (guard.py), result shaping
                                   │
                                   ▼
   engine.py   Engine protocol: search, filter, get, context, notes, feedback
               (InMemoryEngine here; your retrieval stack in production)
```

| Module | Responsibility | Depends on FastMCP |
|---|---|---|
| `server.py` | Transport shell. Builds the `FastMCP` server, wires Auth0 and the encrypted token store, resolves the token subject, registers the nine tools, runs the HTTP transport. | yes |
| `config.py` | Reads and validates every environment setting that affects authentication, token storage and the bind address. Fails closed. | no |
| `kernel.py` | All tool behavior, with the subject as an explicit parameter. | no |
| `guard.py` | Sliding-window rate limit and the JSONL audit log. | no |
| `engine.py` | The `Engine` protocol and the dependency-free `InMemoryEngine`. | no |
| `instructions.py` | Server instructions and the per-tool annotations, with a drift test. | no (uses `mcp.types`) |

The shell is deliberately thin: each `@mcp.tool` function resolves the subject
from the access token and calls one kernel method. Because the subject is a
parameter, not ambient request state, the security-critical logic is unit-tested
without any protocol or auth machinery (`tests/test_kernel.py`). The shell itself
is covered by transport tests (`tests/test_transport.py`) that drive it through
the official clients on both protocol eras.

## 2. Tools and engine calls

| Tool | Kernel method | Engine calls |
|---|---|---|
| `soma_search` | `search` | `search` + `filter_relevant` |
| `soma_get` | `get` | `get_chunk` |
| `soma_debug` | `debug` | `search` + `filter_relevant` (both stages returned) |
| `soma_context` | `context` | `assemble_context` (the full pipeline, optional deep round) |
| `soma_whoami` | (shell only) | none, reads the access token |
| `soma_write` | `write` | `add_note` |
| `soma_update` | `update` | `full_note` + `update_note` |
| `soma_delete` | `delete` | `full_note` + `delete_note` |
| `soma_feedback` | `feedback` | `log_feedback` |

A production engine typically backs these with vector search, an LLM relevance
filter and a multi-step orchestration; the kernel does not care. Keeping the
same engine behind a web UI and the MCP server means both answer a question the
same way.

## 3. Cross-cutting guards

Enforced centrally in the kernel, never per tool:

- **Access** (`subject_check`): every tool except `soma_whoami` requires the
  subject in `MCP_TOEGANG_SUBJECTS`; writes also require `MCP_SCHRIJF_SUBJECTS`.
  Fail closed unless `MCP_SINGLE_USER=1`.
- **Rate limit and audit** (`guard.py`): per-subject sliding window on every
  call; one JSONL line per write action in `$SOMA_DATA/mcp_audit.jsonl`.
- **Data-boundary fence** (`_fence`): every memory string is prefixed with a
  marker that it is data, not instructions.

And in the shell:

- **Error masking:** `FastMCP(..., mask_error_details=True)`.
- **Fail-closed configuration** (`config.py`): partial Auth0 or storage settings
  stop startup.
- **Network exposure:** loopback bind and Host/Origin validation when
  unauthenticated.

See [`security.md`](security.md) for the threat model.

## 4. Protocol eras

FastMCP 4 on the MCP Python SDK v2 serves both protocol eras from one endpoint.
A 2026-07-28 client calls `server/discover` and sends protocol metadata with
every request; no session exists. A handshake-era client (2024-11-05 to
2025-11-25) sends `initialize` and receives an `Mcp-Session-Id`. The SDK routes
each request by its `MCP-Protocol-Version` header. SOMA's tools need nothing from
the client (no sampling, elicitation or roots), so they behave identically in
both eras. Details: [`specification.md`](specification.md).

## 5. Deployment shape

A typical self-hosted deployment, kept generic on purpose:

- the server runs as a non-root container or service, listening on
  `0.0.0.0:8000` inside a private network;
- a TLS-terminating reverse proxy or tunnel is the only public entry; the
  container port is never published directly;
- `SOMA_DATA` is a persistent volume owned by the service user, holding the
  encrypted OAuth store (`mcp_oauth/`) and the audit log;
- secrets (`AUTH0_CLIENT_SECRET`, `MCP_JWT_SIGNING_KEY`,
  `MCP_STORAGE_ENCRYPTION_KEY`) come from the platform's secret store, never
  from Git;
- legacy (handshake-era) clients hold sessions in process memory, so more than
  one worker needs sticky routing; 2026-07-28 clients do not.

## 6. Releases versus deployments

This public repository **releases**; it does not **deploy**.

- **Public reference release** (here): a reviewed PR, green CI, an annotated
  tag `vX.Y.Z` approved by Onno, and the tag-triggered workflow that builds,
  attests and publishes a GitHub Release. See [`RELEASE.md`](../RELEASE.md).
- **Private SOMA production deployment** (elsewhere): the production system
  consumes a released version through its own private delivery pipeline, with
  its own approvals, smoke tests and rollback. Its scripts, hosts and topology
  are intentionally not part of this repository.

## 7. Why this shape

- **Sovereignty:** one instance per memory, self-hosted, your own keys.
- **Compatibility:** the protocol layer is the official stack (FastMCP and the
  MCP Python SDK), so off-the-shelf clients work without glue.
- **Testability:** the FastMCP-free kernel, guard and config modules carry the
  security-critical logic and are fully unit-tested; transport tests cover the
  shell.
- **Replaceable engine:** the same tools, guards and fence in front of any
  retrieval stack that implements `Engine`.
