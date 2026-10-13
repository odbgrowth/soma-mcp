# Security Policy

SOMA MCP is a reference implementation of a **private, self-hosted** Model
Context Protocol server. It exposes a single person's memory to autonomous
agents, so security is a first-class concern. See [`docs/security.md`](docs/security.md)
for the full threat model (fail-closed access, per-subject rate limiting, write
audit logging, the two-step delete, and the prompt-injection data-boundary
fence).

## Reporting a vulnerability

**Please report security issues privately. Do not open a public issue.**

Preferred: use GitHub's **private vulnerability reporting** on this repository
(the **Security** tab → **Report a vulnerability**). This opens a private advisory
visible only to the maintainer.

If you cannot use that, you may instead open a regular issue that contains **only**
a request to be contacted, without any vulnerability details, and we will
arrange a private channel.

Please include, where possible:

- a description of the issue and its impact;
- the affected version (`soma-mcp --version`) and component (for example
  `kernel.py`, `guard.py`, `server.py`, `config.py`, the auth flow);
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

Security fixes go into the latest minor release only. While the project is
`0.x`, upgrade to the newest minor to receive fixes; there is no long-term
support branch.

| Version | Supported |
|---------|-----------|
| 0.2.x | Yes |
| 0.1.x (untagged initial publication) | No: uses the pickle-based `DiskStore` token store (CVE-2025-69872); upgrade to 0.2.x, see [`docs/upgrading.md`](docs/upgrading.md) |
| `main` between releases | Best effort; fixes land here first |

## Scope and hardening notes

- The bundled **`InMemoryEngine` is for demos and tests only**: substring search,
  notes in process memory. It is not a secure or durable backend.
- Without the `AUTH0_*` variables the server runs **unauthenticated**, binds to
  `127.0.0.1` and validates `Host`/`Origin` against DNS rebinding. Never expose
  an unauthenticated instance to a network. For any networked deployment
  configure OAuth 2.1 and the fail-closed allowlists (`MCP_TOEGANG_SUBJECTS`,
  `MCP_SCHRIJF_SUBJECTS`) as described in [`docs/auth.md`](docs/auth.md).
- A partial Auth0 or token-storage configuration refuses to start; it never
  falls back to an unauthenticated or plaintext mode.
- Terminate TLS in front of the server (reverse proxy or tunnel); do not publish
  the server port directly.
- Treat all memory returned by the tools as **data, not instructions**: the
  server fences it, but downstream agents must honor that boundary.
- Release artifacts carry `SHA256SUMS` and a GitHub build-provenance attestation;
  verify them as described in [`RELEASE.md`](RELEASE.md#9-post-release-verification).

## Out of scope

- Vulnerabilities in third-party dependencies (FastMCP, the MCP Python SDK,
  Auth0): please report those to their projects, though we welcome a heads-up.
  CI audits the dependency set with pip-audit on every change.
- Misconfigurations of a self-hosted deployment (e.g. running unauthenticated on
  a public network) are operator responsibility, not a defect in this code.
