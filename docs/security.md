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
- The **local machine** in unauthenticated mode: there is no identity, so every
  process and user on the machine that can reach the port has the access the
  allowlists grant (full access with `MCP_SINGLE_USER=1`). Web pages in a browser
  on that machine are kept out by the Host/Origin guard (§4).

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

Without Auth0 the server is a local experiment, and `serve()` (which the
`soma-mcp` command uses) keeps it one:

- it binds to **127.0.0.1** unless `MCP_HOST` says otherwise, and logs a warning
  when an unauthenticated server is bound to a non-loopback address;
- it validates `Host` and `Origin` strictly (FastMCP `host_origin_protection=True`)
  on any bind address: the `Host` must be `127.0.0.1`, `localhost`, `::1`, the
  address the request arrived on, or a host listed in
  `FASTMCP_HTTP_ALLOWED_HOSTS`, and a browser `Origin` must match (or be listed
  in `FASTMCP_HTTP_ALLOWED_ORIGINS`). A web page
  in your browser therefore cannot reach the server through **DNS rebinding**
  (HTTP 421/403). The official conformance scenario `dns-rebinding-protection`
  and an in-process test cover it;
- it still applies the allowlists: without `MCP_SINGLE_USER=1` every call is
  denied.

If you mount `build_server(...)` in your own ASGI app or call its `run()`
yourself, the guard is yours to enable (`host_origin_protection=True`); FastMCP
leaves it off by default. In `serve()` as well as in your own mount, FastMCP
adds `FASTMCP_HTTP_ALLOWED_HOSTS` and `FASTMCP_HTTP_ALLOWED_ORIGINS` (from the
environment or a `.env` file in the working directory) to the guard's lists; a
wildcard such as `["*"]` in either switches the corresponding check off, so
leave both unset on an unauthenticated server.

Authenticated deployments bind to `0.0.0.0` by default (inside a private
network, behind the proxy) and leave the guard to FastMCP's own setting, off by
default: every request needs a bearer token, which a rebinding page does not
have, and a reverse proxy forwards the public `Host` header that a default guard
would reject. To validate `Host`/`Origin` there as well, set
`FASTMCP_HTTP_HOST_ORIGIN_PROTECTION=true` and list your public host in
`FASTMCP_HTTP_ALLOWED_HOSTS` as a JSON array, for example
`FASTMCP_HTTP_ALLOWED_HOSTS='["mcp.example.com"]'`; a plain or comma-separated
value fails FastMCP's settings validation and stops startup. The server also
skips FastMCP's startup banner and its update check against PyPI, so it makes no
unsolicited outbound request.

## 5. OAuth token storage

Issued OAuth state lives in a **Fernet-encrypted `FileTreeStore`** on the data
volume (`$SOMA_DATA/mcp_oauth/`) when `MCP_JWT_SIGNING_KEY` and
`MCP_STORAGE_ENCRYPTION_KEY` are set:

- a stolen volume snapshot yields no usable tokens without the key;
- one JSON file per entry, no code execution on read (0.1.x used `DiskStore`,
  whose `diskcache` backend unpickles: CVE-2025-69872);
- key and collection names are sanitized (FastMCP's V1 strategies replace
  unsafe characters and add a hash suffix), so a client-supplied, URL-shaped
  client id cannot steer a path;
- entries whose ciphertext does not decrypt (rotated key, tampering) read as
  missing;
- the pre-0.2 `mcp_tokens/` directory is never read; the server warns while it
  exists. Never restore it from a backup.

Fernet provides **confidentiality, not integrity of the store as a whole**: the
upstream wrapper returns an entry that was written without encryption as-is,
and a ciphertext copied from one entry into another still decrypts. Someone who
can write to `mcp_oauth/` could therefore plant client registrations or swap
token entries without the key. The server refuses to start if the directory
belongs to an account other than the service user or root (its owner can
always make it writable again), restricts it to mode 0700 on every start, and
refuses to start if that fails while the directory is writable by group or
others, or is not writable by the service user itself (a root-owned 0700
directory under a non-root service would otherwise fail on the first client
registration). Keep the data volume writable by the service user only. (With
`DiskStore`, the same write access meant code execution.)

## 6. Prompt-injection fence (egress)

Memory can contain text that addresses the calling agent ("ignore your previous
instructions and…"). The kernel treats every memory text it returns as data:

- `kernel._fence` prefixes each one with a marker stating it is stored memory
  and that embedded commands must not be executed: the text of `soma_search`,
  `soma_get` and `soma_context`, the `soma_debug` snippets and filter
  explanation, and the `soma_delete` preview;
- the fence is applied centrally in the kernel; tests check each of these
  paths in the kernel, and search, debug and the delete preview also through
  the MCP protocol;
- short metadata labels (`datum`, `herkomst`, `domein`, `gesprekstitel`) are not
  fenced, and the fence is a prefix, not an enclosing pair: in `soma_context`
  it marks the start of the assembled text.

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
  declared floors of the direct dependencies (pip-audit), and on committed
  secrets (gitleaks, full history). It also runs weekly on `main`, so a newly
  published advisory turns it red without a code change.
- The conformance job installs the official suite from
  `tools/conformance/package-lock.json` (every transitive package pinned with an
  integrity hash) with `npm ci --ignore-scripts`. The job has a read-only token
  and its output feeds no release artifact.
- GitHub Actions are pinned to commit SHAs; workflows default to read-only
  tokens, and only the release's `publish` job can write. That job installs and
  runs no third-party Python.
- Release artifacts are built by a job that runs only the hash-pinned build
  front end and backend, and are hashed at once. Within the release run, the
  wheel's dependencies run in a separate read-only smoke job and in the CI jobs
  of `verify`, which never handle the release artifacts. `publish` checks the
  artifacts against the build digests (exact file set), validates the smoke
  output and the release state before it records a GitHub build-provenance
  attestation (`gh attestation verify`), assembles the release notes from
  trusted job outputs and attaches the wheel, the sdist and `SHA256SUMS` to the
  release. The wheel is reproducible from the tag (`RELEASE.md` §8, §9).

## 12. Operator checklist

Before exposing an instance:

- [ ] All five Auth0 settings present; the startup log does not say "running
      WITHOUT authentication".
- [ ] `MCP_TOEGANG_SUBJECTS` set to your own subject(s). Avoid
      `MCP_SINGLE_USER=1` with Auth0: it admits every account that can sign in
      to the Auth0 application (the server warns).
- [ ] `MCP_SCHRIJF_SUBJECTS` set (a subset of the above).
- [ ] `MCP_JWT_SIGNING_KEY` and `MCP_STORAGE_ENCRYPTION_KEY` set from a secret
      store; `$SOMA_DATA` on a persistent volume readable and writable only by
      the service user.
- [ ] Public access only through the TLS proxy or tunnel.
- [ ] No pre-0.2 `mcp_tokens/` directory left on the volume.
- [ ] The startup log does not show the fail-closed warning.
