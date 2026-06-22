# Security Model

SOMA MCP's threat model is shaped by one fact: it exposes **a single person's
entire memory** to autonomous agents over a public network path. The defenses
are layered accordingly, and several are specific to the *self-hosted, private
instance* posture rather than generic API hardening.

## 1. Trust boundaries

```
[ MCP client / agent ]  ──TLS──▶  [ Cloudflare Tunnel ]  ──▶  [ soma-mcp :8000 ]
        untrusted                  TLS terminates here          OAuth + guards
                                                                     │
                                                            [ SOMA engine + data ]
```

- The **network** is untrusted; TLS terminates at the tunnel and the container
  port is never directly exposed.
- The **client** is authenticated but only *partially* trusted — a valid token
  is necessary but not sufficient (see §2).
- The **memory contents** are treated as potentially hostile *to the calling
  agent* (prompt injection — see §5).

## 2. Authentication and fail-closed authorization

Authentication is OAuth 2.1 via Auth0 (`Auth0Provider`), establishing the token
`subject`. On top of that, SOMA enforces its own allowlists on **every** call:

- `toegang(subject)` gates all reads against `MCP_TOEGANG_SUBJECTS`.
- `schrijfrecht(subject)` gates all writes against `MCP_SCHRIJF_SUBJECTS`
  (defense-in-depth *on top of* read access).
- **Fail-closed by construction.** `subject_check` returns a denial when the
  allowlist env var is empty — unless `MCP_SINGLE_USER=1` is explicitly set. A
  blank or unset `.env` line therefore *closes* the server rather than opening it
  to the world. The shell also logs a loud warning at startup when neither an
  allowlist nor the single-user flag is present.

This two-key model (valid OAuth token **and** allowlisted subject) is the core of
the "private" guarantee: even a correctly-issued token from your Auth0 tenant
cannot read your memory unless its subject is on the list.

## 3. Rate limiting

`soma_guard.rate_limit_check` applies a **sliding-window per-subject** limit
across all tools (`MCP_RATE_LIMIT`, default 30 calls/minute; `0` disables it).
The motivation is concrete: nearly every tool call costs a Haiku invocation, so
an agent stuck in a loop would otherwise quietly burn budget. The limiter also
self-prunes: it caps tracked subjects (`_MAX_SUBJECTS = 10_000`) and evicts
expired entries, so a caller cycling through forged subjects cannot grow memory
unbounded.

## 4. Audit logging

Every **write** action (`soma_write`, `soma_update`, `soma_delete`) appends one
JSONL line to `mcp_audit.jsonl` on the data volume: timestamp, subject, tool, and
target. This is multi-user hygiene — *who did what, when*. Logging is best-effort
and never blocks a write (an `OSError` is swallowed): the audit trail must not
become a denial-of-service surface on the primary action.

## 5. Prompt-injection data-fencing (egress)

The memory can contain text that *looks like an instruction to the calling
agent* — a note or imported document that says "ignore your previous
instructions and…". SOMA treats all returned memory as **data, not
instructions**:

- Every memory string the server returns passes through `_omhein`, which prefixes
  an explicit boundary marker stating the content is stored memory and that
  embedded commands must not be executed — only used as a source.
- The fence is applied **centrally in the kernel**, so no read tool
  (`soma_search`, `soma_get`, `soma_context`) can accidentally bypass it.

This does not *prevent* a downstream model from being manipulated, but it gives
every compliant client an unambiguous signal to treat the payload as untrusted
data, which is the strongest egress-side mitigation a memory server can offer.

## 6. Error masking (no internal leakage)

`FastMCP(..., mask_error_details=True)` returns a generic message for unexpected
exceptions instead of a traceback. This matters because a raw traceback from a
retrieval pipeline could leak filesystem paths, query internals, or fragments of
other memory. Deliberately-raised `ToolError` messages still reach the client, so
intended, safe errors (validation, rate-limit, access) remain informative.

## 7. Write-path safety valves

- **Size caps:** `soma_write`/`soma_update` reject text over `MAX_NOTE_TEKENS`
  (25,000 chars), mirroring the UI limit, to prevent MB-scale notes via the MCP.
- **Type guards:** `soma_update`/`soma_delete` only operate on `note-*` ids, so a
  caller cannot mutate imported source chunks.
- **Two-step delete:** `soma_delete` without `bevestig=true` returns only a
  *preview*; the destructive action requires an explicit second call. This forces
  a human-readable confirmation step before any deletion.

## 8. Deployment hardening

- Containers run **non-root**, with a uid aligned to the data-volume owner.
- The MCP port (`8000`) is reached only through the Cloudflare Tunnel; it is not
  published to the host network for public traffic.
- OAuth tokens are stored **Fernet-encrypted** on disk, so a stolen volume
  snapshot does not yield usable tokens without the encryption key.
- Deploys go through a gated straat that refuses drift from `origin/main` and
  runs a smoke test before tagging a release.

## 9. Operator checklist

Before exposing an instance:

- [ ] `MCP_TOEGANG_SUBJECTS` set to your own subject(s) — or `MCP_SINGLE_USER=1`
      *only* if you genuinely intend a single-user instance.
- [ ] `MCP_SCHRIJF_SUBJECTS` set (a subset of the above) if writes should be
      restricted further.
- [ ] `MCP_RATE_LIMIT` appropriate for your usage (default 30/min is sane).
- [ ] `MCP_JWT_SIGNING_KEY` + `MCP_STORAGE_ENCRYPTION_KEY` set for persistent,
      encrypted token storage.
- [ ] Public access only via the tunnel; container port not published directly.
- [ ] Confirm the startup log does **not** show the fail-closed warning.
