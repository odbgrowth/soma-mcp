# MCP compliance overview

SOMA MCP against the official Model Context Protocol, revision **2026-07-28**,
with the older handshake revisions it also serves. This page separates what
SOMA's own CI **tests**, what it **delegates** to FastMCP and the MCP Python
SDK, what it **leaves out on purpose**, and what is **roadmap**.

> **Summary.** SOMA MCP implements a tested, tools-only MCP profile on the
> official stack (FastMCP `>=4.1,<5`, MCP Python SDK `>=2.3,<3`). Its CI drives
> the server through the official clients on both protocol eras and runs the
> applicable scenarios of the official MCP conformance suite. It does not claim
> full conformance: resources, prompts, completions and logging are not
> implemented, and protocol mechanics SOMA does not touch are delegated to the
> SDK.

## Status legend

- **Tested**: covered by this repository's CI (pytest or the conformance job).
- **Delegated**: provided by FastMCP / the MCP SDK; SOMA neither overrides nor
  independently tests it beyond the smoke paths.
- **Not implemented (optional)**: optional in the specification; deliberately
  absent.
- **Roadmap**: worth doing; listed in §7.

## 1. Base protocol

| Requirement | Status | Evidence / notes |
|---|---|---|
| JSON-RPC 2.0 framing | Delegated | SDK. Wire validity checked by the conformance suite's `wire-schema-valid` check. |
| 2026-07-28: `server/discover`, per-request `_meta`, no sessions | Tested | `tests/test_transport.py` (modern client, in memory and over HTTP); conformance `server-stateless` at 2026-07-28 (23 of 25 checks; 2 baselined, see §6). |
| Handshake era: `initialize` lifecycle (2024-11-05 to 2025-11-25) | Tested | `tests/test_transport.py` with `mode="legacy"`; conformance `server-initialize`, `ping`. |
| Protocol version negotiation and `UnsupportedProtocolVersionError` | Tested (via conformance) | `server-stateless` checks; SOMA does not pin a revision. |
| `serverInfo` (name, version) | Tested | `SOMA` and `soma_mcp.__version__`, asserted on both eras and over HTTP. |
| `instructions` | Tested | `DiscoverResult` / `InitializeResult`; asserted equal to `build_instructions()`. Clients differ in whether they show it to the model, so the critical rules are repeated in the tool descriptions. |
| Error objects | Delegated (protocol) / Tested (tools) | Protocol errors come from the SDK. Tool denials are results with an `error` field; masked internal errors are tested. |

## 2. Transport

| Requirement | Status | Notes |
|---|---|---|
| Streamable HTTP | Tested | Real HTTP server on 127.0.0.1 in pytest and in the conformance job. |
| DNS-rebinding protection (Host/Origin validation) for local servers | Tested | Conformance `dns-rebinding-protection` against the unauthenticated loopback server. |
| stdio | Not implemented (optional) | SOMA is a long-running networked server. |
| TLS | Deployment | Terminated by the operator's proxy or tunnel. |

## 3. Server capabilities

| Capability | Status | Notes |
|---|---|---|
| `tools` | Tested | Nine tools; `tools/list` and `tools/call` on both eras; conformance `tools-list` at 2025-11-25 and 2026-07-28. |
| `listChanged` / `subscriptions/listen` | Not implemented (optional) | The tool set is static. |
| `resources` | Not implemented (optional) | Memory is reached through retrieval tools, not URI enumeration. |
| `prompts` | Not implemented (optional) | Retrieval prompts live inside the engine. |
| `completions` | Not implemented (optional) | Low value for this surface. |
| `logging` | Not implemented (optional) | Server-side logs and the write audit log instead; the capability is deprecated in 2026-07-28. |

A server advertising only `tools` is a valid MCP server: every other server
capability is optional.

## 4. Tools

| Aspect | Status | Notes |
|---|---|---|
| Name, description, `inputSchema` | Tested | Every schema is `type: object`; tool names match the conformance naming rule. |
| Argument validation | Delegated | FastMCP validates arguments against the derived schema. |
| Structured results | Tested | Every tool returns JSON in `structuredContent`; asserted per tool. |
| Declared `outputSchema` | Roadmap | Results are structured but not yet described by an explicit output schema. |
| Annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | Tested | All four explicit for every tool; the wire bytes are asserted to use the camelCase names. |
| Error signaling | Tested | Denials as `error` results; unexpected exceptions masked (`isError: true`, no traceback). |

## 5. Authentication and authorization

| Requirement | Status | Notes |
|---|---|---|
| OAuth 2.1 authorization | Delegated (+ construction tested) | FastMCP `Auth0Provider`; SOMA tests that its configuration builds the provider against a local OIDC discovery document. No real Auth0 in CI. |
| Protected resource metadata, authorization server metadata, dynamic client registration | Delegated | FastMCP's OAuth proxy. |
| Bearer token → subject → allowlist | Tested | End to end over HTTP with FastMCP's static token verifier: owner, reader, stranger and forged tokens. |
| Fail-closed allowlists and configuration | Tested | Kernel and config tests. |
| Persistent, encrypted token storage | Tested | Encrypted at rest, survives a restart, wrong key reads as missing, URL-shaped keys sanitized. |

## 6. Conformance suite

CI runs `tools/run_conformance.sh` against `soma-mcp` started in the documented
local mode, with pinned suite versions:

| Suite | Scenario | Revision | Result |
|---|---|---|---|
| `@modelcontextprotocol/conformance@0.1.16` | `server-initialize`, `tools-list`, `ping` | 2025-era | pass |
| same | `dns-rebinding-protection` | 2025-11-25 | pass |
| `@modelcontextprotocol/conformance@0.2.0-alpha.12` | `tools-list` | 2025-11-25 and 2026-07-28 | pass |
| same | `server-stateless` | 2026-07-28 | pass with 2 baselined checks |

The two baselined checks call `test_missing_capability`, a fixture tool only the
suite's reference server registers. They are listed one by one in
[`.github/conformance-baseline.yml`](../.github/conformance-baseline.yml), so
every other check still gates. The remaining server scenarios need fixture
tools, resources or prompts that SOMA does not have and do not run. The
2026-07-28 scenarios come from a pinned alpha release of the suite, the first
to cover that revision.

## 7. Roadmap

1. Declare `outputSchema` per tool. *(medium)*
2. Run the conformance requirement sets (`--requirements 2026-07-28`) once a
   stable suite release covers the modern revision. *(small)*
3. Smoke-test real clients (Claude, ChatGPT, an IDE) against a staging instance
   before releases. *(medium, manual)*
4. A read-only `resources` view of recent or pinned notes, if clients want
   browsing rather than querying. *(larger, evaluate demand first)*
5. Decide on 2026-07-28 extensions (for example tasks) if a tool ever needs
   them. *(watch)*

Done in 0.2.0: explicit `serverInfo.version`, documented protocol support with
tests for both eras, a conformance job, and tool annotations verified on the
wire.
