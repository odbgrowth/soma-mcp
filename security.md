# Security Policy

SOMA MCP is a reference implementation of a **private, self-hosted** Model
Context Protocol server. It exposes a single person's memory to autonomous
agents, so security is a first-class concern — see [`docs/security.md`](docs/security.md)
for the full threat model (fail-closed access, per-subject rate limiting, write
audit logging, the two-step delete, and the prompt-injection data-boundary
fence).

## Reporting a vulnerability

**Please report security issues privately — do not open a public issue.**

Preferred: use GitHub's **private vulnerability reporting** on this repository
(the **Security** tab → **Report a vulnerability**). This opens a private advisory
visible only to the maintainer.

If you cannot use that, you may instead open a regular issue that contains **only**
a request to be contacted — without any vulnerability details — and we will
arrange a private channel.

Please include, where possible:

- a description of the issue and its impact;
- the affected component (e.g. `kernel.py`, `guard.py`, `server.py`, auth flow);
- steps to reproduce or a proof of concept;
- any suggested remediation.

### What to expect

- **Acknowledgement:** we aim to confirm receipt within a few days.
- **Assessment:** we will validate and assess severity, and keep you updated.
- **Fix & disclosure:** we will work on a fix and coordinate disclosure with you.
  Please give us reasonable time to remediate before any public disclosure.

We appreciate responsible disclosure and are happy to credit reporters in the
release notes (let us know if you prefer to remain anonymous).

## Supported versions

This is an evolving reference implementation. Security fixes target the latest
`main`. There is no long-term support branch yet; pin a commit if you depend on
it in production and watch the repository for updates.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| older commits | ⚠️ best-effort; please upgrade |

## Scope and hardening notes

- The bundled **`InMemoryEngine` is for demos and tests only** — it performs
  substring search and stores notes in process memory. It is **not** a secure or
  durable backend. Provide your own `Engine` for real use.
- The server runs **unauthenticated** when the `AUTH0_*` variables are unset
  (with a loud warning). **Never expose an unauthenticated instance to a
  network.** For any networked deployment, configure OAuth 2.1 and the
  fail-closed subject allowlists (`MCP_TOEGANG_SUBJECTS` / `MCP_SCHRIJF_SUBJECTS`)
  as described in [`docs/auth.md`](docs/auth.md) and [`docs/security.md`](docs/security.md).
- Terminate TLS in front of the server (e.g. a reverse proxy or tunnel); do not
  publish the container port directly.
- Treat all memory content returned by the tools as **data, not instructions** —
  the server fences it, but downstream agents must honor that boundary.

## Out of scope

- Vulnerabilities in third-party dependencies (FastMCP, the `mcp` SDK, Auth0) —
  please report those to their respective projects, though we welcome a heads-up.
- Misconfigurations of a self-hosted deployment (e.g. running unauthenticated on
  a public network) are operator responsibility, not a defect in this code.
