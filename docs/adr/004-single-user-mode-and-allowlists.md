# ADR-004: Single-user mode never opens a missing allowlist next to a configured one

Status: Accepted (approved by Onno on 2026-11-19). Changes the authorization
trust boundary, which needs Onno's explicit approval before merge
([`AGENTS.md`](../../AGENTS.md)).

Date: 2026-11-19

## Context

`MCP_SINGLE_USER=1` is the deliberate way to run without allowlists: the local
quick start, one person, no `MCP_TOEGANG_SUBJECTS`. Until now the flag was read
per allowlist: any allowlist that was empty counted as open.

That made one configuration fail open. With `MCP_SINGLE_USER=1`, a filled
`MCP_TOEGANG_SUBJECTS` and an empty `MCP_SCHRIJF_SUBJECTS`, every subject on the
access list could also write, update and delete. No warning was logged, because
the existing warning only fires when the access list is empty.

## Decision

Single-user mode applies only when `MCP_TOEGANG_SUBJECTS` is empty. As soon as
an access allowlist is configured, the instance is no longer single-user and
every allowlist fails closed again: an empty `MCP_SCHRIJF_SUBJECTS` then means
nobody writes.

The rule lives in the kernel (`src/soma_mcp/kernel.py`), so it also holds for
code that uses `soma_mcp.Kernel` directly.

## Alternatives considered

Refusing to start when `MCP_SINGLE_USER=1` is combined with any allowlist. It is
stricter, but a startup check sits in the transport shell and does not cover
direct use of the public `Kernel` API.

## Consequences

- An operator who relied on the old behavior (single-user mode plus an access
  list, no write list) loses write access after upgrading and must set
  `MCP_SCHRIJF_SUBJECTS`.
- `MCP_SINGLE_USER=1` without an access list behaves as before, including the
  startup warning when Auth0 is configured.
- A write allowlist without an access list keeps its meaning under single-user
  mode: access is open, writing is limited to the listed subjects.
