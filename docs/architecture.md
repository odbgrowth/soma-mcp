# Architecture

How SOMA MCP is built, and how it sits in front of the SOMA retrieval engine.
The guiding principle is a **private instance**: one person's memory, one
deployment, one set of keys.

## 1. The shell / kernel split

SOMA MCP is two files with a strict separation of concerns:

```
soma_mcp.py        — transport shell: Auth0 setup, resolve token subject,
                     register the 9 tools on FastMCP. Thin by design;
                     nothing here deserves a unit test.

soma_mcp_kern.py   — tool logic: guards, validation, execution, result shaping.
                     FastMCP-free, so every handler is unit-testable without an
                     Auth0 environment (tests/test_mcp_kern.py).
```

The shell is *dumb*; the kernel is *covered*. Each `@mcp.tool` function does one
thing — resolve the subject from the access token and delegate to a `kern_*`
function with that subject as an explicit parameter. Because the subject is a
parameter (not pulled from request context inside the kernel), the guards and
handlers test cleanly with no protocol or auth machinery.

```
client ──HTTP/JSON-RPC──▶ FastMCP ──▶ @mcp.tool (shell) ──▶ kern_* (kernel)
                            │             │                     │
                       handshake,    resolve subject       guards → validate
                       auth, schema   from access token     → execute → shape
```

## 2. The shared pipeline

The kernel does **not** reimplement retrieval. It calls the same engine the
Streamlit UI uses:

- `soma_core.zoek` — vector search (pgvector) returning a candidate pool.
- `soma_core.filter_chunks_met_haiku` — relevance filtering via a forced Haiku
  tool-call.
- `soma_orkest.verzamel_context` — the full orchestration: sub-question
  decomposition, health aggregation, type-pull on list questions, optional
  deep-search round.
- `soma_notes` — note write / update / delete / fetch.
- `soma_feedback.log_feedback` — dogfood feedback log (feeds `/autotune`).

**Architecture rule:** everything below `soma_app.py` is Streamlit-free. The UI
and the MCP share the entire pipeline through `soma_orkest.verzamel_context`, so
an answer to the same question is identical whether it came from the web UI or
from an agent over MCP. The MCP is not a second-class path — it is the path the
owner actually uses (the Streamlit UI is effectively unused; tunnel traffic goes
to `/mcp`).

## 3. Tool-to-engine mapping

| Tool | Kernel handler | Engine call |
|---|---|---|
| `soma_search` | `kern_search` | `zoek` + `filter_chunks_met_haiku` |
| `soma_get` | `kern_get` | `collection.get` |
| `soma_debug` | `kern_debug` | `zoek` + `filter_chunks_met_haiku` (both stages exposed) |
| `soma_context` | `kern_context` | `soma_orkest.verzamel_context` (full pipeline, optional deep search) |
| `soma_whoami` | (shell only) | reads the access token claims |
| `soma_write` | `kern_write` | `soma_notes.voeg_note_toe` |
| `soma_update` | `kern_update` | `soma_notes.update_note` |
| `soma_delete` | `kern_delete` | `soma_notes.verwijder_note` |
| `soma_feedback` | `kern_feedback` | `soma_feedback.log_feedback` |

## 4. Cross-cutting guards

Three concerns are enforced centrally, not per tool:

- **Access guards** (`soma_mcp_kern`): every read passes `toegang(subject)`;
  every write passes `schrijfrecht(subject)`. Fail-closed.
- **Rate limiting & audit** (`soma_guard`): a sliding-window per-subject rate
  limit on every call, and a JSONL audit line per *write* action
  (`mcp_audit.jsonl` on the data volume). The module has no FastMCP import, so
  it is unit-testable in isolation.
- **Data-boundary fencing** (`soma_mcp_kern._omhein`): every memory string the
  server returns is wrapped with an explicit "this is data, not instructions"
  marker — a single choke point so no read tool can bypass it.

See [`security.md`](security.md) for the threat model these implement.

## 5. Deployment topology

SOMA MCP runs as a container in the SOMA deployment:

- **Production:** container `soma-mcp` on port `8000`, alongside the UI container
  `soma` (`:8501`). Staging mirrors this (`soma-mcp-staging` `:8001`), and a demo
  tenant runs `soma-mcp-demo` (`:8010`, from `tenants/voorbeeld/`).
- **Public access:** via Cloudflare Tunnel (`soma.usesiva.net`,
  `demo.usesiva.net`). The MCP port is never exposed directly; TLS terminates at
  the tunnel.
- **Non-root containers:** the containers run as a non-root uid aligned to the
  data-volume owner, so bind-mount writes keep working.
- **Token persistence:** OAuth tokens live in a Fernet-encrypted `DiskStore` on
  the data volume, so a rebuild needs no connector reconnect.
- **Cold-start mitigation:** the server preloads the embedding model at startup;
  `deploy_prod.sh` polls for readiness instead of sleeping.

Deploys go *only* through the deploy straat (`tools/deploy_staging.sh`,
`tools/deploy_prod.sh`), never a manual `compose up` on prod. `deploy_prod.sh`
refuses if the checkout differs from `origin/main`, runs a smoke test (containers
up, UI `:8501`, MCP `:8000`, retrieval gold-color in-container) and tags a
release on success.

## 6. Why this shape

- **Sovereignty:** one instance per memory, self-hosted, behind your own tunnel
  and keys. No shared backend.
- **Compatibility:** the protocol layer is the reference stack (FastMCP/`mcp`),
  so off-the-shelf clients work without bespoke glue.
- **Testability:** the FastMCP-free kernel and guard modules mean the security-
  critical logic is covered without standing up an auth environment.
- **Single source of truth:** UI and MCP answer from the same pipeline, so there
  is no drift between "what the app says" and "what the agent says".
