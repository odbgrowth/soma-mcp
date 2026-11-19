# Decisions

Accepted architecture decisions live in `docs/adr/`.

- ADR-001: vendor-neutral Claude Code and Codex foundation.
- ADR-002: `soma-mcp` is the sole approved public repository.
- ADR-003 (accepted 2026-10-13): MCP Python SDK v2, FastMCP 4 and
  protocol 2026-07-28; encrypted `FileTreeStore` for OAuth state; fail-closed
  configuration; loopback bind and DNS-rebinding guard without authentication;
  one version source and tag-driven releases.
- ADR-004 (accepted 2026-11-19): single-user mode applies only without an access
  allowlist; next to a configured one, a missing allowlist fails closed.
