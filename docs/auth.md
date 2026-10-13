# Authentication and scoped access

SOMA MCP uses **OAuth 2.1** for authentication (the MCP authorization mechanism)
and adds **subject allowlists** for authorization. Together they implement the
"private memory" guarantee: a valid token is necessary but not sufficient.

## 1. OAuth 2.1 through Auth0

With the five Auth0 settings present, the shell builds FastMCP 4's
`Auth0Provider` (an OIDC proxy with fixed Auth0 application credentials):

```python
from fastmcp.server.auth.providers.auth0 import Auth0Provider

auth = Auth0Provider(
    config_url=config.config_url,        # AUTH0_CONFIG_URL (OIDC discovery URL)
    client_id=config.client_id,          # AUTH0_CLIENT_ID
    client_secret=config.client_secret,  # AUTH0_CLIENT_SECRET
    audience=config.audience,            # AUTH0_AUDIENCE
    base_url=config.base_url,            # BASE_URL (public URL of this server)
    **persistence,                       # jwt_signing_key + client_storage, see §2
)
```

`config` comes from `soma_mcp.config.load_auth_config()`, which reads only
explicit environment variables (FastMCP's own environment settings are not
used) and is **all-or-nothing**:

| Environment | Result |
|---|---|
| no `AUTH0_*` variable set | local, unauthenticated reference server (warns, loopback only) |
| all four `AUTH0_*` and `BASE_URL` set | authenticated server |
| anything in between | `ConfigurationError`: the server refuses to start |

A missing variable therefore never downgrades a production setup to an open
server. Error messages name the missing variables and never print values.

The provider implements the MCP authorization flow: OAuth protected resource
metadata (RFC 9728), authorization server metadata (RFC 8414), dynamic client
registration (RFC 7591) and client ID metadata documents, with Auth0 as the
upstream identity provider. For a user it is "connect, sign in at Auth0,
connected". In the Auth0 application, set the allowed callback URL to
`BASE_URL` + `/auth/callback`.

## 2. Token storage

FastMCP's OAuth proxy keeps state: registered clients, issued tokens and the
upstream tokens behind them.

**With `MCP_JWT_SIGNING_KEY` and `MCP_STORAGE_ENCRYPTION_KEY`** (both required
together, and only with Auth0) SOMA passes:

- `jwt_signing_key`: signs the tokens FastMCP issues, so they stay valid across
  restarts;
- `client_storage`: a `FileTreeStore` in `$SOMA_DATA/mcp_oauth/`, wrapped in
  `FernetEncryptionWrapper` with `MCP_STORAGE_ENCRYPTION_KEY`. One encrypted JSON
  file per entry; key and collection names go through FastMCP's V1 sanitization
  strategies, so URL-shaped client ids are hashed instead of becoming paths.

Generate the encryption key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
An invalid key stops startup. Entries that no longer decrypt (after a key
rotation, or tampering) read as missing: the client registers again. Nothing is
ever read or written as plaintext.

**Without them**, FastMCP 4's default applies: the signing key is derived from
`AUTH0_CLIENT_SECRET`, and the store is an encrypted `FileTreeStore` in the
platform's user data directory. That directory is usually not on a persistent
volume in containers, so a rebuild forces every client to reconnect.

**Before 0.2.0** the store was a `DiskStore` in `$SOMA_DATA/mcp_tokens/`. It is
pickle-based (CVE-2025-69872) and is never read by 0.2.0; see
[`upgrading.md`](upgrading.md).

## 3. Subjects

The **subject** (`sub`) identifies the authenticated principal. The shell reads
it from the verified access token:

```python
def _subject() -> str | None:
    token = get_access_token()  # fastmcp.server.dependencies
    return None if token is None else _token_subject(token)  # token.subject or claims["sub"]
```

`None` means "unauthenticated": no allowlist ever contains it, so it only gets
through in deliberate single-user mode.

To find your subject, call **`soma_whoami`**. It is deliberately not behind the
access guard, so a newly connected user can always read their own subject,
client id and scopes:

```json
{"subject": "auth0|abc123", "client_id": "...", "scopes": ["openid"], "expires_at": "1781000000"}
```

On the unauthenticated reference server it returns
`{"subject": null, "note": "unauthenticated reference server"}`.

## 4. Read and write access

Authorization is enforced in the kernel on every call:

| Guard | Function | Variable | Applies to |
|---|---|---|---|
| Rate limit | `guard.rate_limit_check` | `MCP_RATE_LIMIT` | every tool except `soma_whoami` |
| Instance access | `Kernel._access` → `subject_check` | `MCP_TOEGANG_SUBJECTS` | every tool except `soma_whoami` |
| Write access | `Kernel._write_access` → `subject_check` | `MCP_SCHRIJF_SUBJECTS` | `soma_write`, `soma_update`, `soma_delete` |

- Allowlists are comma-separated subjects; surrounding spaces are ignored.
- Write access is checked **on top of** instance access, never instead of it.
- A denial is a normal tool result with an `error` field, for example
  `{"error": "no write access for this token (subject: auth0|abc123)"}`, so the
  calling model can read and explain it.

## 5. Fail-closed semantics

```text
allowlist empty? ── MCP_SINGLE_USER exactly "1"? ── yes: allow (single-user mode)
                                                 └─ no : deny
subject not in allowlist? ── deny
```

A blank or missing allowlist line closes the server instead of opening it. The
shell logs a startup warning when neither an allowlist nor single-user mode is
configured.

## 6. Typical configurations

Your own instance:

```bash
MCP_TOEGANG_SUBJECTS=auth0|yourSubjectId
MCP_SCHRIJF_SUBJECTS=auth0|yourSubjectId
# or, deliberately and only for a single-user instance:
MCP_SINGLE_USER=1
```

Shared read, owner write:

```bash
MCP_TOEGANG_SUBJECTS=auth0|owner,auth0|trustedReader
MCP_SCHRIJF_SUBJECTS=auth0|owner
```

## 7. Rate limit

`MCP_RATE_LIMIT` (default `30`) caps calls per minute per subject in a sliding
60-second window; `0` disables it. Most real engines call an LLM per tool call,
so this is a cost guardrail as much as an abuse guardrail. A limited call
returns `{"error": "rate-limit: at most 30 calls per minute for this subject …"}`.
