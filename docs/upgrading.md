# Upgrading

## 0.1.x → 0.2.0

0.2.0 moves the server to FastMCP 4 on the MCP Python SDK v2 and the MCP
2026-07-28 protocol revision, replaces the OAuth token store, and makes the
configuration fail closed. Decision record: [ADR-003](adr/003-mcp-sdk-v2-fastmcp4-upgrade.md).

### At a glance

| | 0.1.x | 0.2.0 |
|---|---|---|
| FastMCP | `>=3.4.2` | `>=4.1,<5` |
| MCP Python SDK | `>=1.27.2` | `>=2.3,<3` |
| MCP protocol | handshake era (2025-11-25 and older) | **2026-07-28**, plus 2024-11-05 to 2025-11-25 |
| Python | 3.10+ (tested on 3.12) | 3.10 to 3.14 (all tested) |
| OAuth token store | `DiskStore` at `$SOMA_DATA/mcp_tokens/` | encrypted `FileTreeStore` at `$SOMA_DATA/mcp_oauth/` |
| Bind without Auth0 | `0.0.0.0:8000` | `127.0.0.1:8000` (`MCP_HOST`/`MCP_PORT`) |
| `serverInfo.version` | FastMCP's version | SOMA MCP's version |

### Upgrade steps for an operator

1. **Install** the new version (`pip install -U` from the release wheel or the
   `v0.2.0` tag). `pip check` should report no conflicts; FastMCP 4 needs
   pydantic `>=2.12` and Starlette `>=1.0.1`.
2. **Check the configuration.** 0.2.0 refuses to start where 0.1.x silently
   degraded:
   - set **all** of `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`,
     `AUTH0_AUDIENCE` and `BASE_URL`, or none of the `AUTH0_*` variables;
   - set **both** `MCP_JWT_SIGNING_KEY` and `MCP_STORAGE_ENCRYPTION_KEY`, or
     neither; they are rejected without Auth0;
   - `MCP_STORAGE_ENCRYPTION_KEY` must be a Fernet key:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Keep the same `MCP_JWT_SIGNING_KEY` as before.
3. **Bind address.** An authenticated server still listens on `0.0.0.0:8000`.
   An unauthenticated one now listens on `127.0.0.1:8000`; set `MCP_HOST` only
   if you really need it reachable from elsewhere (the server warns).
4. **Start the server** and look for two log lines: the startup line
   `soma-mcp 0.2.0 (fastmcp …, mcp …; protocol 2026-07-28, …)`, and, if an old
   store exists, the warning about the pre-0.2 `DiskStore` directory.
5. **Reconnect clients once.** The new token store starts empty, so every
   connector (Claude, ChatGPT, Cursor, VS Code, custom agents) goes through the
   OAuth flow again on its next request. Interactive clients prompt by
   themselves; headless agents holding a refresh token need a manual reconnect.
   Subjects do not change, so `MCP_TOEGANG_SUBJECTS`/`MCP_SCHRIJF_SUBJECTS` stay
   valid.
6. **Delete the old store** once clients work again:
   `rm -r "$SOMA_DATA/mcp_tokens"`. Do not copy it anywhere and do not keep it in
   backups you might restore: it is pickle-based (CVE-2025-69872).

### Why the token store changed and why there is no migration

`DiskStore` is backed by `diskcache`, which deserializes with `pickle`. Anyone
able to write into the token directory could make the server execute code on
its next read. The replacement writes one Fernet-encrypted JSON file per key,
with key and collection names sanitized so a client-supplied id can never steer
a file path. A migration would have to unpickle the old files, which is exactly
the risk being removed; one re-registration per client is the safer price.

Rotating `MCP_STORAGE_ENCRYPTION_KEY` later has the same effect: entries that no
longer decrypt read as missing and clients register again.

Fernet keeps the entries confidential at rest; it does not stop someone who can
write to `mcp_oauth/` from planting or swapping entries. 0.2.0 restricts the
directory to mode 0700; keep the data volume writable by the service user only.

### Protocol and client impact

- The server answers `server/discover` (2026-07-28) and `initialize` (older
  revisions) on the same `/mcp` endpoint; the client's SDK picks. Nothing to
  configure.
- On 2026-07-28 connections there are no sessions; a load balancer needs no
  stickiness for modern clients. Handshake-era clients still use
  `Mcp-Session-Id`; with more than one worker they need sticky routing.
- Tool names, parameters, annotations and result shapes are unchanged. One
  exception: a rate-limited call now returns `{"error": "rate-limit: …"}` like
  every other denial (0.1.x used `fout`).
- Server instructions are delivered in `DiscoverResult.instructions`
  (2026-07-28) or `InitializeResult.instructions` (handshake era).

### For code that embeds SOMA MCP

- `build_server(engine)`, `Engine`, `InMemoryEngine`, `Kernel` and `main` keep
  their signatures. `build_server` now raises
  `soma_mcp.config.ConfigurationError` for a partial Auth0 or storage setup.
- New: `soma_mcp.serve(engine)` runs your engine with the same bind address and
  DNS-rebinding guard as `soma-mcp`. Calling `build_server(...).run(...)`
  yourself skips that guard unless you pass `host_origin_protection=True`.
- `cryptography>=50` is now a base dependency (it was only implied before).
- If you used the MCP SDK v1 client (`ClientSession`, `streamablehttp_client`),
  move to `mcp.Client`; see [`examples.md`](examples.md). Headers such as
  `Authorization` go on an `httpx2.AsyncClient` passed to
  `streamable_http_client(url, http_client=...)`.
- `mcp.types` fields are snake_case in Python (`tool.input_schema`,
  `annotations.read_only_hint`); the JSON on the wire is unchanged.
- FastMCP 4 raises `httpx2` exceptions; an `except httpx.…` around FastMCP calls
  silently stops matching.

### Rollback to 0.1.x

Possible but not recommended: it brings back the `DiskStore` vulnerability.

1. Reinstall the 0.1.x code (pin the previous commit; there is no `v0.1.0` tag).
2. Start with an **empty** `$SOMA_DATA/mcp_tokens/` and let clients re-register.
   Never restore an old `mcp_tokens/` from a backup.
3. Remember that 0.1.x binds to `0.0.0.0` even without Auth0.

The new `$SOMA_DATA/mcp_oauth/` directory can stay in place for a later
re-upgrade or be deleted.
