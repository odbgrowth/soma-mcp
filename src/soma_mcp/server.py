"""
server.py — the FastMCP transport shell.

Thin by design: optional Auth0 setup, resolve the token subject, and hang the
tools on FastMCP. All logic (guards, validation, execution) lives in kernel.py
and is tested there without an auth environment — this shell holds nothing that
deserves a unit test. The docstrings below are the tool descriptions clients see.

This mirrors SOMA's production `soma_mcp.py`. Two differences make it runnable as
a public reference:
  * the retrieval engine is injected (defaults to the in-memory reference engine);
  * Auth0 is optional — without AUTH0_* env vars the server runs unauthenticated
    for local experimentation (and warns loudly).
"""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP

from .engine import Engine, InMemoryEngine
from .kernel import Kernel

log = logging.getLogger("soma_mcp")


def _build_auth():
    """Return an Auth0Provider if configured, else None (unauthenticated)."""
    if not os.environ.get("AUTH0_CONFIG_URL"):
        log.warning("AUTH0_CONFIG_URL not set -> running WITHOUT authentication. "
                    "For any networked deployment, configure Auth0 (see README).")
        return None

    from fastmcp.server.auth.providers.auth0 import Auth0Provider

    # Persistent token storage: without this the issued OAuth tokens (JTI admin)
    # live only in process memory and the signing key is random per start — every
    # rebuild would force a connector reconnect. With MCP_JWT_SIGNING_KEY +
    # MCP_STORAGE_ENCRYPTION_KEY, tokens survive a restart (encrypted DiskStore).
    persistence = {}
    if os.environ.get("MCP_JWT_SIGNING_KEY") and os.environ.get("MCP_STORAGE_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet
        from key_value.aio.stores.disk import DiskStore
        from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
        persistence = {
            "jwt_signing_key": os.environ["MCP_JWT_SIGNING_KEY"],
            "client_storage": FernetEncryptionWrapper(
                key_value=DiskStore(directory=os.path.join(
                    os.environ.get("SOMA_DATA", "."), "mcp_tokens")),
                fernet=Fernet(os.environ["MCP_STORAGE_ENCRYPTION_KEY"]),
            ),
        }
    return Auth0Provider(
        config_url=os.environ["AUTH0_CONFIG_URL"],
        client_id=os.environ["AUTH0_CLIENT_ID"],
        client_secret=os.environ["AUTH0_CLIENT_SECRET"],
        audience=os.environ["AUTH0_AUDIENCE"],
        base_url=os.environ["BASE_URL"],
        **persistence,
    )


def build_server(engine: Engine | None = None) -> FastMCP:
    """Construct the FastMCP server over an engine (in-memory by default)."""
    # Fail-closed startup check: without an allowlist AND without a deliberate
    # single-user flag, every tool call is denied. Warn loudly so a blank .env
    # line stands out immediately.
    if (not os.environ.get("MCP_TOEGANG_SUBJECTS", "").strip()
            and os.environ.get("MCP_SINGLE_USER", "").strip() != "1"):
        log.warning("MCP fail-closed: MCP_TOEGANG_SUBJECTS unset and "
                    "MCP_SINGLE_USER!=1 -> all access will be denied")

    kernel = Kernel(engine or InMemoryEngine())

    # mask_error_details=True: unexpected exceptions return a generic message
    # instead of an internal traceback (which could leak paths, queries or memory
    # fragments). Explicitly raised ToolError messages still pass through.
    mcp = FastMCP("SOMA", auth=_build_auth(), mask_error_details=True)

    def _subject():
        """Subject of the current token (or None when unauthenticated)."""
        try:
            from fastmcp.server.dependencies import get_access_token
            token = get_access_token()
        except Exception:
            return None
        return getattr(token, "subject", None) or (token.claims or {}).get("sub")

    @mcp.tool
    def soma_search(query: str, limit: int = 15) -> list[dict]:
        """Search SOMA memory. Returns filtered chunks with metadata."""
        return kernel.search(_subject(), query, limit)

    @mcp.tool
    def soma_get(id: str) -> dict:
        """Fetch one chunk from SOMA by id."""
        return kernel.get(_subject(), id)

    @mcp.tool
    def soma_debug(query: str, limit: int = 25) -> dict:
        """Diagnostics: retrieval per stage. Stage 1 = raw search, stage 2 =
        after relevance filtering. limit bounds both lists."""
        return kernel.debug(_subject(), query, limit)

    @mcp.tool
    def soma_context(question: str, max_tokens: int = 30000, deep: bool = False) -> dict:
        """Full retrieval pipeline for a question: decomposition into sub-questions,
        health aggregation, type-pull on list questions and relevance filtering —
        the same route the SOMA app uses. Returns the assembled context; formulate
        the answer from it. Use this for health and composite questions; use
        soma_search for isolated lookups. deep=true (deep search): a second search
        round over reformulations that excludes all first-round sources — use it
        when the normal answer looks incomplete (slower; finds what round one missed)."""
        return kernel.context(_subject(), question, max_tokens, deep)

    @mcp.tool
    def soma_whoami() -> dict:
        """Identity of the current token: subject, client and scopes. Use the
        subject to configure MCP_TOEGANG_SUBJECTS (instance owner) or
        MCP_SCHRIJF_SUBJECTS (write access). Deliberately NOT behind the access
        guard: a mistakenly-connected user must be able to read their own subject."""
        try:
            from fastmcp.server.dependencies import get_access_token
            t = get_access_token()
        except Exception:
            return {"subject": None, "note": "unauthenticated reference server"}
        return {"subject": getattr(t, "subject", None) or (t.claims or {}).get("sub"),
                "client_id": t.client_id, "scopes": t.scopes, "expires_at": str(t.expires_at)}

    @mcp.tool
    def soma_write(text: str) -> dict:
        """Add a new note to SOMA. Returns the number of chunks stored. Only for
        facts/memories — feedback goes via soma_feedback, and correcting an
        existing note via soma_update (prevents duplicates)."""
        return kernel.write(_subject(), text)

    @mcp.tool
    def soma_update(base_id: str, new_text: str) -> dict:
        """Overwrite an existing note with new text — use this for corrections
        instead of adding another note (prevents duplicates). base_id e.g.
        note-20260608-151003. Chunk ids change."""
        return kernel.update(_subject(), base_id, new_text)

    @mcp.tool
    def soma_feedback(question: str, verdict: str, answer: str = "", comment: str = "",
                      causes: list[str] | None = None,
                      source_ids: list[str] | None = None) -> dict:
        """Log dogfood feedback about a SOMA answer to the feedback log — NOT to
        memory (use soma_write only for facts, never for feedback). verdict:
        'yes', 'partially' or 'no'. causes (optional): keyword, sources, prompt,
        model, question too vague, unknown. The log feeds the improvement loop."""
        return kernel.feedback(_subject(), question, verdict, answer, comment,
                               causes, source_ids)

    @mcp.tool
    def soma_delete(base_id: str, confirm: bool = False) -> dict:
        """Delete a note (all its chunks) by base id, e.g. note-20260608-081905.
        Safety valve: without confirm=true you get only a preview — review it with
        the user, then call again with confirm=true."""
        return kernel.delete(_subject(), base_id, confirm)

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp = build_server()
    # Streamable HTTP at /mcp on port 8000 — the current MCP transport.
    mcp.run(transport="http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
