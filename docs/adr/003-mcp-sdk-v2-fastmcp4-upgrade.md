# ADR-003: MCP Python SDK v2, FastMCP 4 and protocol 2026-07-28

Status: Proposed. Changes the protocol stack, OAuth token storage and the local
trust boundary, so it needs Onno's explicit approval before merge
([`AGENTS.md`](../../AGENTS.md)).

Date: 2026-10-13

## Context

SOMA MCP 0.1.0 ran on FastMCP 3 (`fastmcp>=3.4.2`) and MCP Python SDK 1
(`mcp>=1.27.2`), both unbounded upward, and documented MCP revision 2025-11-25.
Upstream moved on (verified 2026-10-13 against PyPI and the official sources):

- MCP revision **2026-07-28** is the current stable specification ("latest" in
  the specification repository). It removes the `initialize` handshake and
  sessions: requests carry protocol metadata in `_meta`, servers implement
  `server/discover`.
- **MCP Python SDK 2** (`mcp` 2.0.0 on 2026-07-28, 2.3.0 current) speaks
  2026-07-28 and still negotiates the handshake revisions 2024-11-05 to
  2025-11-25 on the same endpoint. Protocol types moved to `mcp-types`
  (re-exported as `mcp.types`) with snake_case attributes and unchanged
  camelCase wire names.
- **FastMCP 4** (`github.com/PrefectHQ/fastmcp`; 4.0.0 on 2026-08-31, 4.1.0
  current) builds on SDK v2. Its upgrade guide lists no change SOMA's code needed
  beyond what is below; SOMA uses no elicitation, sampling, background tasks or
  session state, which are the areas that changed behavior.
- `DiskStore` (py-key-value, backed by `diskcache`) unpickles its files:
  **CVE-2025-69872**. FastMCP dropped `diskcache` and defaults to an encrypted
  `FileTreeStore`. SOMA still configured `DiskStore` explicitly.

The inventory also found defects the upgrade surfaced:

- every tool call failed in the documented local (unauthenticated) mode, on
  FastMCP 3 and 4 alike: the shell dereferenced a `None` access token;
- `serverInfo.version` reported FastMCP's version, not SOMA's;
- a partial Auth0 configuration (any variable but `AUTH0_CONFIG_URL`) silently
  started an unauthenticated server bound to `0.0.0.0`;
- the official conformance suite's `dns-rebinding-protection` scenario failed:
  FastMCP 4 leaves Host/Origin validation off by default, so a web page in the
  user's browser could reach the local single-user server through a rebound DNS
  name.

### Migration matrix (inventory, before editing)

| Area | 0.1.0 | 0.2.0 | Kind | Action |
|---|---|---|---|---|
| FastMCP | `>=3.4.2` (unbounded) | `>=4.1,<5` | runtime | migrate, bound |
| MCP Python SDK | `>=1.27.2` (unbounded) | `>=2.3,<3` | runtime | migrate, bound, keep direct |
| Protocol | docs: 2025-11-25, 2026-07-28 "draft" | 2026-07-28 + handshake revisions | docs | update, test both eras |
| Tool annotations | camelCase `dict` | `mcp.types.ToolAnnotations` (snake_case) | runtime | migrate, wire test |
| `get_access_token()` | unguarded `None` dereference | `None` = unauthenticated | runtime | fix |
| Token store | `DiskStore` + Fernet | `FileTreeStore` (V1 sanitization) + Fernet | runtime | security migration |
| Auth configuration | inferred from `AUTH0_CONFIG_URL` only | all-or-nothing, fails closed | runtime | harden |
| Bind address | always `0.0.0.0:8000` | loopback without auth; `MCP_HOST`/`MCP_PORT` | runtime | harden |
| DNS rebinding | not validated | Host/Origin guard for the loopback server | runtime | harden |
| `serverInfo.version` | FastMCP's version | `soma_mcp.__version__` | runtime | fix |
| Version source | `pyproject.toml` + `__init__.py` | `__init__.py` only (setuptools dynamic) | packaging | unify |
| Client examples | `ClientSession` + `streamablehttp_client` | `mcp.Client` (+ `httpx2` for headers) | docs | migrate, execute in tests |
| Python SDK test import | `mcp.types.ToolAnnotations(**camelCase)` | typed objects | test | migrate |
| FastMCP repository links | `jlowin/fastmcp` | `PrefectHQ/fastmcp` | docs | update |
| Deployment claims | `tools/deploy_*.sh`, private hosts | generic guidance | docs | remove |
| CI | one job, Python 3.12 | quality, 3.10 to 3.14, floor, security, package, conformance | CI | replace |
| Release | none | tag workflow, checksums, attestation | CI | add |

## Decision

1. **Adopt FastMCP 4 and MCP Python SDK 2** with bounded ranges
   `fastmcp>=4.1,<5` and `mcp>=2.3,<3`. The floors are the newest minors at the
   time of the decision; CI proves them (dependency-floor job) and the newest
   versions inside the ranges (test matrix). `mcp` stays a direct dependency:
   SOMA imports `mcp.types` and documents the SDK `Client`.
2. **Serve MCP 2026-07-28 as the primary revision** and the handshake revisions
   through the SDK's per-request negotiation. SOMA adds no era-specific code.
   Both eras are tested in memory and over Streamable HTTP; the official
   conformance suite runs in CI for the applicable tools-only scenarios.
3. **Replace `DiskStore` with an encrypted `FileTreeStore`** at
   `$SOMA_DATA/mcp_oauth/`, using FastMCP's V1 key and collection sanitization
   and `FernetEncryptionWrapper(raise_on_decryption_error=False)`. The old
   `mcp_tokens/` directory is never read; startup logs a warning when it exists.
   No automatic migration: reading the old store means unpickling it.
4. **Fail closed on configuration.** Auth0 requires all four `AUTH0_*`
   variables plus `BASE_URL`; token storage requires both keys and Auth0; an
   invalid Fernet key stops startup. Messages name variables, never values.
5. **Narrow the unauthenticated trust boundary.** Without Auth0 the server binds
   to `127.0.0.1` (overridable with `MCP_HOST`, with a loud warning for
   non-loopback) and validates Host/Origin (FastMCP `host_origin_protection="auto"`).
   Authenticated deployments keep `0.0.0.0` and FastMCP's default (no
   Host/Origin guard): every request carries a bearer token, and a reverse proxy
   on the same host forwards the public `Host` header the guard would reject.
6. **One version source.** `soma_mcp.__version__` feeds the package metadata,
   `serverInfo.version`, `soma-mcp --version` and the required tag `v{version}`.
   This release is **0.2.0**: the protocol stack and a storage format change,
   which is a minor bump under 0.x; 1.0.0 stays a deliberate API decision.

## Alternatives considered

- **Stay on FastMCP 3 / SDK 1.** Rejected: no 2026-07-28 support, unbounded
  ranges already resolve to the new majors, and the `DiskStore` CVE remains.
- **Depend on FastMCP only, drop `mcp`.** Rejected: SOMA imports `mcp.types`
  directly; relying on a transitive dependency for direct imports breaks when
  FastMCP changes its own pins.
- **Keep `DiskStore` and restrict directory permissions.** Rejected: mitigates
  but keeps a pickle sink in the token path; upstream moved away from it.
- **Migrate old `DiskStore` entries automatically.** Rejected: it requires
  unpickling a file an attacker may have written. One re-registration per client
  is the safe cost.
- **Use FastMCP's default store** (platform data directory, keys derived from the
  client secret). Kept as the behavior when SOMA's storage keys are unset, but
  not the documented production setup: it is lost on a container rebuild
  without a volume and ties the storage key to the OAuth client secret.
- **Refuse to start unauthenticated on a non-loopback address.** Rejected for
  now: local container experiments need it. It takes two explicit settings
  (`MCP_HOST` and `MCP_SINGLE_USER=1`) and logs a warning.
- **Host/Origin guard for authenticated deployments too.** Deferred: it needs a
  host allowlist that matches every proxy setup. Bearer tokens already defeat DNS
  rebinding there.

## Security impact

- Removes a pickle-deserialization sink from the OAuth path (CVE-2025-69872).
- Encrypted at rest as before (Fernet); keys never logged; undecryptable entries
  read as missing, never as plaintext.
- A partial Auth0 setup can no longer start an open server.
- The local single-user server is no longer reachable from the network by
  default, nor from web pages via DNS rebinding.
- Fail-closed allowlists, the prompt-injection fence, error masking, rate limit
  and audit log are unchanged and now tested through the transport as well.
- Supply chain: bounded majors, pip-audit on the runtime set and the floors,
  `cryptography>=50` (first release without known advisories), SHA-pinned
  actions, gitleaks, artifact attestations.

## Compatibility

- Python 3.10 to 3.14 (CI). 3.15 is excluded: the MCP SDK does not declare it.
- Clients: any MCP client on 2026-07-28 or a handshake revision from
  2024-11-05 to 2025-11-25. Tool names, parameters and result shapes are
  unchanged, except the rate-limit denial key (`fout` → `error`).
- Operators: re-register connectors once (new token store); set `MCP_HOST` if an
  unauthenticated server must listen beyond loopback; fix partial configurations
  that 0.1.0 silently accepted.
- Embedders: `build_server`, `Engine`, `InMemoryEngine`, `Kernel`, `main`
  unchanged. `build_server` raises `ConfigurationError` on partial configuration.

## Migration and rollback

Operator steps: [`docs/upgrading.md`](../upgrading.md). Release rollback:
[`RELEASE.md`](../../RELEASE.md#10-rollback). Rolling back to 0.1.x restores
`DiskStore` usage and its CVE; if unavoidable, start from an empty
`mcp_tokens/` and never restore an old one from backup.

## Consequences

- SOMA follows the SDK's era negotiation; it cannot restrict which protocol
  eras it serves (the SDK offers no switch).
- FastMCP's camelCase compatibility bridge is disabled in CI, so a v1-style
  field read fails tests instead of warning.
- Dependabot proposes the next majors as separate PRs; adopting FastMCP 5 or
  SDK 3 needs a new ADR.
- Conformance runs against pinned suite versions, including a 0.2.0 alpha for
  the 2026-07-28 scenarios, with two check-level exceptions documented in
  `.github/conformance-baseline.yml`. Full conformance is not claimed.
