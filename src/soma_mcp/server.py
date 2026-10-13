"""
server.py: the FastMCP transport shell.

Thin by design: optional Auth0 setup, resolve the token subject, and hang the
tools on FastMCP. All logic (guards, validation, execution) lives in kernel.py
and is tested there without an auth environment; configuration parsing lives in
config.py. The docstrings below are the tool descriptions clients see.

This mirrors SOMA's production MCP shell. Two differences make it runnable as a
public reference:
  * the retrieval engine is injected (defaults to the in-memory reference engine);
  * Auth0 is optional: without AUTH0_* env vars the server runs unauthenticated
    for local experimentation, binds to loopback, and warns loudly.

Protocol: FastMCP 4 on the MCP Python SDK v2 serves the sessionless 2026-07-28
revision (server/discover) and the handshake-era revisions (initialize) from the
same endpoint; the SDK negotiates the era per request.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import logging
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from mcp.types.version import HANDSHAKE_PROTOCOL_VERSIONS, LATEST_MODERN_VERSION

from . import __version__
from .config import (
    LEGACY_TOKEN_STORE_DIRNAME,
    AuthConfig,
    ConfigurationError,
    TokenStorage,
    bind_address,
    data_dir,
    is_loopback,
    load_auth_config,
)
from .engine import Engine, InMemoryEngine
from .instructions import ANNOTATIONS, build_instructions
from .kernel import Kernel, single_user

if TYPE_CHECKING:
    from fastmcp.server.auth import AccessToken, AuthProvider
    from key_value.aio.protocols import AsyncKeyValue

log = logging.getLogger("soma_mcp")

SERVER_NAME = "SOMA"


def version_report() -> str:
    """SOMA MCP, FastMCP and MCP SDK versions plus the protocol revisions served.

    Safe to log or print: package versions only, no environment values."""
    return (
        f"soma-mcp {__version__} "
        f"(fastmcp {importlib.metadata.version('fastmcp')}, "
        f"mcp {importlib.metadata.version('mcp')}; "
        f"protocol {LATEST_MODERN_VERSION}, "
        f"legacy handshake {', '.join(HANDSHAKE_PROTOCOL_VERSIONS)})"
    )


def _token_storage(storage: TokenStorage) -> AsyncKeyValue:
    """Fernet-encrypted FileTreeStore for issued OAuth state.

    Replaces the pre-0.2 DiskStore: diskcache unpickles whatever it finds on
    disk (CVE-2025-69872), FileTreeStore writes one JSON file per key. The V1
    sanitization strategies are FastMCP's own defaults: they hash keys and
    collection names that are not filesystem-safe (URL-shaped OAuth client ids,
    "..") so a client-supplied id can never steer a path. Changing them later
    orphans every stored entry, so they are fixed here.
    """
    from cryptography.fernet import Fernet
    from key_value.aio.stores.filetree import (
        FileTreeStore,
        FileTreeV1CollectionSanitizationStrategy,
        FileTreeV1KeySanitizationStrategy,
    )
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

    try:
        fernet = Fernet(storage.encryption_key)
    except (ValueError, TypeError):
        # `from None`: never chain an exception that could carry key material.
        raise ConfigurationError(
            "MCP_STORAGE_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe "
            "base64-encoded bytes). Generate one with: python -c \"from "
            "cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from None

    directory = storage.directory
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = FileTreeStore(
        data_directory=directory,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(directory),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(directory),
    )
    # Undecryptable entries (rotated key, tampering) read as missing, so the
    # client re-registers instead of the OAuth endpoints failing. Nothing is
    # ever returned or written in plaintext.
    return FernetEncryptionWrapper(key_value=store, fernet=fernet, raise_on_decryption_error=False)


def _warn_on_legacy_token_store() -> None:
    legacy = data_dir() / LEGACY_TOKEN_STORE_DIRNAME
    if legacy.exists():
        log.warning(
            "Found a pre-0.2 DiskStore token directory at %s. It is no longer read "
            "(diskcache/pickle, CVE-2025-69872); clients re-register once. Delete it "
            "after the upgrade (see docs/upgrading.md).", legacy)


def _build_auth(config: AuthConfig | None) -> AuthProvider | None:
    """Return an Auth0Provider for a complete config, else None (unauthenticated)."""
    if config is None:
        log.warning("Auth0 not configured -> running WITHOUT authentication. For any "
                    "networked deployment, configure Auth0 (see docs/auth.md).")
        return None

    from fastmcp.server.auth.providers.auth0 import Auth0Provider

    # Without explicit storage FastMCP 4 derives its signing and storage keys
    # from AUTH0_CLIENT_SECRET and keeps an encrypted store in the platform data
    # directory, which a container rebuild without a volume loses. With
    # MCP_JWT_SIGNING_KEY + MCP_STORAGE_ENCRYPTION_KEY the store lives on the
    # SOMA data volume and connectors survive rebuilds.
    persistence: dict[str, Any] = {}
    if config.storage is not None:
        _warn_on_legacy_token_store()
        persistence = {
            "jwt_signing_key": config.storage.jwt_signing_key,
            "client_storage": _token_storage(config.storage),
        }
    return Auth0Provider(
        config_url=config.config_url,
        client_id=config.client_id,
        client_secret=config.client_secret,
        audience=config.audience,
        base_url=config.base_url,
        **persistence,
    )


def _token_subject(token: AccessToken) -> str | None:
    subject = token.subject or token.claims.get("sub")
    return str(subject) if subject is not None else None


def _subject() -> str | None:
    """Subject of the current token, or None when the server is unauthenticated."""
    token = get_access_token()
    return None if token is None else _token_subject(token)


def build_server(engine: Engine | None = None) -> FastMCP:
    """Construct the FastMCP server over an engine (in-memory by default).

    Raises ConfigurationError if the environment describes a partial Auth0 or
    token-storage setup.
    """
    # Fail-closed startup check: without an allowlist AND without a deliberate
    # single-user flag, every tool call is denied. Warn loudly so a blank .env
    # line stands out immediately.
    if not os.environ.get("MCP_TOEGANG_SUBJECTS", "").strip() and not single_user():
        log.warning("MCP fail-closed: MCP_TOEGANG_SUBJECTS unset and "
                    "MCP_SINGLE_USER!=1 -> all access will be denied")

    kernel = Kernel(engine or InMemoryEngine())

    # mask_error_details=True: unexpected exceptions return a generic message
    # instead of an internal traceback (which could leak paths, queries or memory
    # fragments). Explicitly raised ToolError messages still pass through.
    # instructions= reaches clients in DiscoverResult (2026-07-28) or
    # InitializeResult (handshake era); clients treat it differently (some inject
    # it into the model's context, some don't), so the rules that matter also
    # live in the individual tool docstrings below. version= is serverInfo.version.
    mcp = FastMCP(SERVER_NAME, instructions=build_instructions(), version=__version__,
                  auth=_build_auth(load_auth_config()), mask_error_details=True)

    @mcp.tool(annotations=ANNOTATIONS["soma_search"])
    def soma_search(query: str, limit: int = 15) -> list[dict[str, Any]]:
        """Search SOMA memory. Returns filtered chunks with metadata."""
        return kernel.search(_subject(), query, limit)

    @mcp.tool(annotations=ANNOTATIONS["soma_get"])
    def soma_get(id: str) -> dict[str, Any]:
        """Fetch one chunk from SOMA by id."""
        return kernel.get(_subject(), id)

    @mcp.tool(annotations=ANNOTATIONS["soma_debug"])
    def soma_debug(query: str, limit: int = 25) -> dict[str, Any]:
        """Diagnostics: retrieval per stage. Stage 1 = raw search, stage 2 =
        after relevance filtering. limit bounds both lists."""
        return kernel.debug(_subject(), query, limit)

    @mcp.tool(annotations=ANNOTATIONS["soma_context"])
    def soma_context(question: str, max_tokens: int = 30000, deep: bool = False
                     ) -> dict[str, Any]:
        """Full retrieval pipeline for a question: decomposition into sub-questions,
        health aggregation, type-pull on list questions and relevance filtering —
        the same route the SOMA app uses. Returns the assembled context; formulate
        the answer from it. Use this for health and composite questions; use
        soma_search for isolated lookups. deep=true (deep search): a second search
        round over reformulations that excludes all first-round sources — use it
        when the normal answer looks incomplete (slower; finds what round one missed)."""
        return kernel.context(_subject(), question, max_tokens, deep)

    @mcp.tool(annotations=ANNOTATIONS["soma_whoami"])
    def soma_whoami() -> dict[str, Any]:
        """Identity of the current token: subject, client and scopes. Use the
        subject to configure MCP_TOEGANG_SUBJECTS (instance owner) or
        MCP_SCHRIJF_SUBJECTS (write access). Deliberately NOT behind the access
        guard: a mistakenly-connected user must be able to read their own subject."""
        token = get_access_token()
        if token is None:
            return {"subject": None, "note": "unauthenticated reference server"}
        return {"subject": _token_subject(token), "client_id": token.client_id,
                "scopes": token.scopes, "expires_at": str(token.expires_at)}

    @mcp.tool(annotations=ANNOTATIONS["soma_write"])
    def soma_write(text: str) -> dict[str, Any]:
        """Add a new note to SOMA. Returns the number of chunks stored. Only for
        facts/memories — feedback goes via soma_feedback, and correcting an
        existing note via soma_update (prevents duplicates)."""
        return kernel.write(_subject(), text)

    @mcp.tool(annotations=ANNOTATIONS["soma_update"])
    def soma_update(base_id: str, new_text: str) -> dict[str, Any]:
        """Overwrite an existing note with new text — use this for corrections
        instead of adding another note (prevents duplicates). base_id e.g.
        note-20260608-151003. Chunk ids change."""
        return kernel.update(_subject(), base_id, new_text)

    @mcp.tool(annotations=ANNOTATIONS["soma_feedback"])
    def soma_feedback(question: str, verdict: str, answer: str = "", comment: str = "",
                      causes: list[str] | None = None,
                      source_ids: list[str] | None = None) -> dict[str, Any]:
        """Log dogfood feedback about a SOMA answer to the feedback log — NOT to
        memory (use soma_write only for facts, never for feedback). verdict:
        'yes', 'partially' or 'no'. causes (optional): keyword, sources, prompt,
        model, question too vague, unknown. The log feeds the improvement loop."""
        return kernel.feedback(_subject(), question, verdict, answer, comment,
                               causes, source_ids)

    @mcp.tool(annotations=ANNOTATIONS["soma_delete"])
    def soma_delete(base_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a note (all its chunks) by base id, e.g. note-20260608-081905.
        Safety valve: without confirm=true you get only a preview — review it with
        the user, then call again with confirm=true."""
        return kernel.delete(_subject(), base_id, confirm)

    return mcp


def main(argv: Sequence[str] | None = None) -> None:
    """Console entry point: `soma-mcp` serves Streamable HTTP at /mcp."""
    parser = argparse.ArgumentParser(
        prog="soma-mcp",
        description="Serve the SOMA MCP reference server over Streamable HTTP at /mcp. "
                    "Configuration comes from environment variables; see .env.example.")
    parser.add_argument("--version", action="store_true",
                        help="print SOMA MCP, FastMCP, MCP SDK and protocol versions and exit")
    if parser.parse_args(argv).version:
        print(version_report())  # argparse's version action would re-wrap the line
        raise SystemExit(0)

    logging.basicConfig(level=logging.INFO)
    try:
        auth_config = load_auth_config()
        host, port = bind_address(authenticated=auth_config is not None)
        mcp = build_server()
    except ConfigurationError as exc:
        raise SystemExit(f"soma-mcp: configuration error: {exc}") from None

    if auth_config is None and not is_loopback(host):
        log.warning("UNAUTHENTICATED server bound to %s: anyone who can reach this "
                    "interface can call the tools. Use MCP_HOST=127.0.0.1 or configure "
                    "Auth0 (see docs/security.md).", host)
    log.info("Starting %s on http://%s:%d/mcp", version_report(), host, port)
    # DNS-rebinding guard: without Host/Origin validation a web page open in the
    # user's browser can reach a loopback server through a rebound DNS name and,
    # in single-user mode, read or delete memory. "auto" validates loopback-bound
    # servers only. Authenticated deployments keep FastMCP's default (off): every
    # request needs a bearer token, and a reverse proxy on the same host forwards
    # the public Host header, which the guard would reject.
    mcp.run(transport="http", host=host, port=port,
            host_origin_protection=False if auth_config is not None else "auto")


if __name__ == "__main__":
    main()
