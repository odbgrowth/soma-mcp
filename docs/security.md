# Security model

SOMA MCP exposes **one person's entire memory** to autonomous agents. The
controls are layered accordingly, and several follow from the self-hosted,
private-instance posture rather than generic API hardening. How to report a
vulnerability: [`../SECURITY.md`](../SECURITY.md).

## 1. Trust boundaries

```text
[ MCP client / agent ] ──TLS──▶ [ reverse proxy / tunnel ] ──▶ [ soma-mcp ]
      untrusted                    TLS terminates here         OAuth + guards
                                                                      │
                                                          [ Engine + data volume ]
```

- The **network** is untrusted. TLS terminates at a proxy or tunnel; the server
  port is never published directly.
- The **client** is authenticated but only partially trusted: a valid token is
  necessary, not sufficient (§2).
- **Memory contents** are treated as potentially hostile to the calling agent
  (prompt injection, §6).
- The **local machine** in unauthenticated mode: other users and web pages on
  the same machine are outside the boundary (§4).

## 2. Authentication and fail-closed authorization

Authentication is OAuth 2.1 through Auth0 (`Auth0Provider`), establishing the
token subject. On top of that the kernel enforces its own allowlists on every
call except `soma_whoami`:

- instance access: subject in `MCP_TOEGANG_SUBJECTS`;
- write access (`soma_write`, `soma_update`, `soma_delete`): additionally in
  `MCP_SCHRIJF_SUBJECTS`;
- **fail closed:** an empty or missing allowlist denies everything unless
  `MCP_SINGLE_USER` is exactly `1`.

Even a correctly issued token from your own Auth0 tenant cannot read the memory
unless its subject is listed. Details: [`auth.md`](auth.md).

## 3. Fail-closed configuration

`soma_mcp.config` refuses to start on configurations that would silently weaken
the server:

- some but not all of `AUTH0_CONFIG_URL`, `AUTH0_CLIENT_ID`,
  `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `BASE_URL`;
- one of `MCP_JWT_SIGNING_KEY` / `MCP_STORAGE_ENCRYPTION_KEY` without the other,
  or either without Auth0;
- an invalid Fernet key, or an `MCP_PORT` that is not a port.

Messages name variables, never values, and secret fields are excluded from the
config objects' `repr`.

## 4. Network exposure of the unauthenticated server

Without Auth0 the server is a local experiment, and its defaults keep it one:

- it binds to **127.0.0.1** unless `MCP_HOST` says otherwise, and logs a warning
  when an unauthenticated server is bound to a non-loopback address;
- it validates `Host` and `Origin` (FastMCP `host_origin_protection="auto"`), so
  a web page in your browser cannot reach it through **DNS rebinding**; the
  official MCP conformance scenario `dns-rebinding-protection` runs in CI;
- it still applies the allowlists: without `MCP_SINGLE_USER=1` every call is
  denied.

Authenticated deployments bind to `0.0.0.0` by default (inside a private
network, behind the proxy) and keep FastMCP's default of no Host/Origin guard:
every request needs a bearer token, which a rebinding page does not have.

## 5. OAuth token storage

Issued OAuth state lives in a **Fernet-encrypted `FileTreeStore`** on the data
volume (`$SOMA_DATA/mcp_oauth/`) when `MCP_JWT_SIGNING_KEY` and
`MCP_STORAGE_ENCRYPTION_KEY` are set:

- a stolen volume snapshot yields no usable tokens without the key;
- one JSON file per entry, no code execution on read (0.1.x used `DiskStore`,
  whose `diskcache` backend unpickles: CVE-2025-69872);
- key and collection names are sanitized (FastMCP's V1 strategies), so a
  client-supplied, URL-shaped client id cannot steer a path;
- entries that do not decrypt read as missing, never as plaintext;
- the pre-0.2 `mcp_tokens/` directory is never read; the server warns while it
  exists. Never restore it from a backup.

## 6. Prompt-injection fence (egress)

Memory can contain text that addresses the calling agent ("ignore your previous
instructions and…"). The kernel treats every returned memory string as data:

- `kernel._fence` prefixes each one with a marker stating it is stored memory
  and that embedded commands must not be executed;
- the fence is applied centrally, so no read tool (`soma_search`, `soma_get`,
  `soma_context`) can bypass it; tests check every read path, in the kernel
  and through the MCP protocol.

This does not make a downstream model immune, but it gives every client an
unambiguous signal, which is the strongest egress-side control a memory server
has. The server instructions repeat the rule.

## 7. Rate limiting

`guard.rate_limit_check` applies a sliding-window limit per subject across all
kernel tools (`MCP_RATE_LIMIT`, default 30 per minute, `0` disables). Real
engines usually call an LLM per tool call, so an agent stuck in a loop would
otherwise burn budget. The limiter caps tracked subjects (`_MAX_SUBJECTS`) and
evicts idle ones, so forged subjects cannot grow memory without bound.

## 8. Audit logging

Every write action (`soma_write`, `soma_update`, `soma_delete`) appends one JSONL
line to `$SOMA_DATA/mcp_audit.jsonl`: time, subject, tool and target (a base id
or a size, never note text). Logging is best effort and never blocks the write.

## 9. Error masking

`FastMCP(..., mask_error_details=True)` replaces unexpected exceptions with a
generic message, so a traceback cannot leak paths, queries or other memory.
Intended denials (access, rate limit, validation) are ordinary results with an
`error` field and stay informative. A transport test feeds an exception through
the server and checks nothing leaks.

## 10. Write-path safety valves

- **Size cap:** `soma_write` and `soma_update` reject text over 25,000
  characters (`MAX_NOTE_CHARS`).
- **Type guard:** `soma_update` and `soma_delete` only accept `note-*` ids, so
  imported source chunks cannot be modified.
- **Two-step delete:** without `confirm=true`, `soma_delete` returns a preview
  only. The tool annotations mark update and delete as destructive.

## 11. Supply chain

- FastMCP and the MCP SDK are bounded below their next major; Dependabot
  proposes new majors as separate pull requests.
- CI fails on known vulnerabilities in the runtime dependency set and in the
  declared floors (pip-audit), and on committed secrets (gitleaks, full history).
- GitHub Actions are pinned to commit SHAs; workflows default to read-only
  tokens, and only the release job can write.
- Release artifacts ship with `SHA256SUMS` and a GitHub build-provenance
  attestation (`gh attestation verify`).

## 12. Operator checklist

Before exposing an instance:

- [ ] All five Auth0 settings present; the startup log does not say "running
      WITHOUT authentication".
- [ ] `MCP_TOEGANG_SUBJECTS` set to your own subject(s), or `MCP_SINGLE_USER=1`
      only for a genuinely single-user instance.
- [ ] `MCP_SCHRIJF_SUBJECTS` set (a subset of the above).
- [ ] `MCP_JWT_SIGNING_KEY` and `MCP_STORAGE_ENCRYPTION_KEY` set from a secret
      store; `$SOMA_DATA` on a persistent volume readable only by the service.
- [ ] Public access only through the TLS proxy or tunnel.
- [ ] No pre-0.2 `mcp_tokens/` directory left on the volume.
- [ ] The startup log does not show the fail-closed warning.
