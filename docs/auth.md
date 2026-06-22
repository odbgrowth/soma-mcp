# Authentication & Scoped Access

SOMA MCP uses **OAuth 2.1** for authentication (the official MCP authorization
mechanism) and adds a **subject allowlist** layer for authorization. The two
together implement the "private memory" guarantee: a valid token is necessary but
not sufficient.

## 1. OAuth 2.1 via Auth0

The transport shell configures an `Auth0Provider`:

```python
auth = Auth0Provider(
    config_url=os.environ["AUTH0_CONFIG_URL"],
    client_id=os.environ["AUTH0_CLIENT_ID"],
    client_secret=os.environ["AUTH0_CLIENT_SECRET"],
    audience=os.environ["AUTH0_AUDIENCE"],
    base_url=os.environ["BASE_URL"],
    **_persistentie,
)
mcp = FastMCP("SOMA", auth=auth, mask_error_details=True)
```

This implements the MCP authorization flow: **Protected Resource Metadata**
(RFC 9728) so clients discover the authorization server, **Authorization Server
Metadata** (RFC 8414) and **Dynamic Client Registration** (RFC 7591) so clients
register and obtain tokens without manual configuration. From the user's side it
is the familiar "connect → redirect to Auth0 → sign in → connected" flow.

### Token persistence

If `MCP_JWT_SIGNING_KEY` and `MCP_STORAGE_ENCRYPTION_KEY` are set, issued tokens
(and the JTI administration / signing key) are stored in a **Fernet-encrypted
`DiskStore`** on the data volume. Without this, tokens live only in process
memory and the signing key is random per start, so every rebuild would force a
client reconnect. With it, you connect once and survive deploys.

## 2. Subjects

The **subject** (`sub`) is the stable identifier of the authenticated principal,
read from the access token:

```python
def _subject():
    token = get_access_token()
    return getattr(token, "subject", None) or (token.claims or {}).get("sub")
```

To find your own subject, call **`soma_whoami`** — it is deliberately *not*
behind the access guard, so a freshly-connected user can always read their own
subject, client id and scopes in order to configure the allowlists.

## 3. Scoped access: read vs write

Authorization is enforced in the kernel as two allowlists plus a rate limit:

| Guard | Function | Env var | Applies to |
|---|---|---|---|
| Rate limit | `rate_limit_check` | `MCP_RATE_LIMIT` | every call |
| Instance access (read) | `toegang` → `subject_check` | `MCP_TOEGANG_SUBJECTS` | all tools |
| Write access | `schrijfrecht` → `subject_check` | `MCP_SCHRIJF_SUBJECTS` | `soma_write`, `soma_update`, `soma_delete` |

- `MCP_TOEGANG_SUBJECTS` and `MCP_SCHRIJF_SUBJECTS` are **comma-separated** lists
  of subjects.
- Write access is **defense-in-depth on top of** read access: `schrijfrecht`
  first calls `toegang`, then additionally checks the write allowlist.
- A denial is returned as a result dict with a `fout` field (e.g.
  `"geen schrijfrecht voor dit token (subject: …)"`), so the calling model can
  read and explain the reason.

## 4. Fail-closed semantics

`subject_check` is fail-closed:

```
allowlist empty?  ──▶  MCP_SINGLE_USER=1 ?  ──▶ yes: allow (single-user mode)
                                              └─▶ no : DENY
subject not in allowlist?  ──▶  DENY
```

An unset or blank allowlist line therefore **closes** the server rather than
opening it. The only way to run without an allowlist is to set `MCP_SINGLE_USER=1`
*on purpose*. The shell logs a startup warning if neither is configured.

## 5. Typical configurations

**Single-user (your own instance):**
```
MCP_SINGLE_USER=1
# or, more explicit and future-proof:
MCP_TOEGANG_SUBJECTS=auth0|yourSubjectId
MCP_SCHRIJF_SUBJECTS=auth0|yourSubjectId
```

**Shared-read, owner-write:**
```
MCP_TOEGANG_SUBJECTS=auth0|owner,auth0|trustedReader
MCP_SCHRIJF_SUBJECTS=auth0|owner
```

## 6. Rate limit

`MCP_RATE_LIMIT` (default `30`) caps calls per minute per subject in a sliding
60-second window. Set `0` to disable. Because most tools invoke Haiku, this is a
cost guardrail as much as an abuse guardrail. A rate-limited call returns a `fout`
explaining the limit.

## 7. What the client sees

After connecting, a client can call `soma_whoami` to confirm identity:

```json
{
  "subject": "auth0|abc123",
  "client_id": "…",
  "scopes": ["…"],
  "expires_at": "2026-06-20 18:00:00"
}
```

Use the returned `subject` to populate `MCP_TOEGANG_SUBJECTS` /
`MCP_SCHRIJF_SUBJECTS`.
