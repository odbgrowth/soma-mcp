# Changelog

All notable changes to SOMA MCP are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Release tags are
`v{version}` and must match `soma_mcp.__version__` (see [`RELEASE.md`](RELEASE.md)).

Three versions are tracked separately and never mixed: the **SOMA MCP package
version** (this file), the **FastMCP / MCP Python SDK** dependency ranges, and
the **MCP protocol revision** the server speaks.

## [Unreleased]

## [0.2.0] - 2026-10-13

First tagged release. `0.1.0` was the untagged initial publication of the
reference implementation (June 2026).

**Stack:** SOMA MCP 0.2.0 · FastMCP `>=4.1,<5` · MCP Python SDK `>=2.3,<3` ·
MCP protocol `2026-07-28`, plus the handshake revisions `2024-11-05` to
`2025-11-25` negotiated by the SDK · Python 3.10 to 3.14.

### Added

- `soma-mcp --version` prints the SOMA MCP, FastMCP and MCP SDK versions and the
  protocol revisions served; the same line is logged at startup.
- `soma_mcp.serve(engine)`: serve a custom `Engine` with the same configuration,
  bind address and DNS-rebinding guard as the `soma-mcp` command.
- `MCP_HOST` and `MCP_PORT` to choose the HTTP bind address explicitly.
- `soma_mcp.config`: FastMCP-free, fail-closed parsing of the Auth0, token
  storage and bind settings, with `ConfigurationError` for partial setups.
- Transport-level tests through the official clients: in memory on both
  protocol eras, and over real Streamable HTTP with the MCP SDK `Client`
  (modern and `mode="legacy"`), including a wire-format check that tool
  annotations serialize as `readOnlyHint`/`destructiveHint`/`idempotentHint`/
  `openWorldHint`, and an end-to-end bearer token to allowlist test.
- Tests for every security invariant (fail-closed access, read vs write
  allowlists, two-step delete, rate limit, prompt-injection fence, error
  masking, audit log), configuration, token storage, version contract and docs.
- CI pipeline (`.github/workflows/ci.yml`): Ruff, mypy, Python 3.10 to 3.14
  test matrix with coverage gate (check names `Python 3.x`, matching the `main`
  ruleset), dependency-floor job that asserts the installed floors
  (`tools/check_floors.py`), documentation checks, pip-audit, gitleaks, package
  build, `twine check` and a clean-wheel smoke test.
- Tag-triggered release workflow (`.github/workflows/release.yml`): tag/version
  and changelog validation, full verification, sdist and wheel, `SHA256SUMS`,
  GitHub artifact attestations and a GitHub Release with notes from this file.
  Nothing is published to PyPI.
- `tools/check_release.py`, `RELEASE.md`, `docs/upgrading.md`,
  ADR-003, Dependabot configuration and a pull request template.
- `py.typed` marker and complete package metadata (classifiers, project URLs,
  PEP 639 license expression).

### Changed

- **FastMCP 3 to FastMCP 4** (`fastmcp>=4.1,<5`) and **MCP Python SDK 1 to 2**
  (`mcp>=2.3,<3`). Both major versions are now bounded.
- The server speaks the stateless **MCP 2026-07-28** revision (`server/discover`,
  per-request protocol metadata) and still serves handshake-era clients
  (`initialize`, up to `2025-11-25`) from the same `/mcp` endpoint.
- The server advertises `serverInfo.version` = the SOMA MCP package version
  (previously FastMCP's own version leaked through).
- One version source: `soma_mcp.__version__`; `pyproject.toml` reads it
  dynamically.
- Tool annotations are typed `mcp.types.ToolAnnotations` objects (snake_case in
  Python, camelCase on the wire).
- Without Auth0 the server now binds to `127.0.0.1` by default instead of
  `0.0.0.0` and validates `Host`/`Origin` strictly. Authenticated deployments
  keep `0.0.0.0` and FastMCP's own guard setting.
- The server no longer shows FastMCP's banner, which also skips its update
  check against PyPI at startup.
- `cryptography>=50` is a base dependency.
- Auth0 and token-storage settings are all-or-nothing: a partial configuration
  refuses to start instead of silently running unauthenticated or without
  persistence. Token-storage variables without Auth0 are rejected too.
- The rate-limit denial uses the `error` key like every other denial (was `fout`).
- Building requires `setuptools>=77` (PEP 639 license metadata).
- Configuration values are stripped of surrounding whitespace.

### Fixed

- Every tool call failed in the unauthenticated local mode (the documented quick
  start) with a masked `AttributeError`, because the shell dereferenced a
  missing access token. `soma_whoami` now reports `subject: null` and the other
  tools reach the fail-closed allowlist as designed.

### Security

- **OAuth token storage moved from `DiskStore` to an encrypted `FileTreeStore`.**
  `DiskStore` is backed by `diskcache`, which deserializes with `pickle`
  (CVE-2025-69872): anyone able to write the token directory could execute code
  in the server. The new store writes one Fernet-encrypted JSON file per key
  under `$SOMA_DATA/mcp_oauth/` with FastMCP's V1 key and collection
  sanitization, so client-supplied ids never become paths. The old
  `$SOMA_DATA/mcp_tokens/` directory is never read; the server logs a warning
  if it still exists. **Clients re-register once after upgrading**
  (see [`docs/upgrading.md`](docs/upgrading.md)).
- An invalid `MCP_STORAGE_ENCRYPTION_KEY` fails at startup with a message that
  never echoes the key; undecryptable entries read as missing. The store
  directory is kept at mode 0700: Fernet protects confidentiality, while the
  store's integrity relies on filesystem permissions (documented).
- The prompt-injection fence now also covers the `soma_debug` snippets and
  filter explanation and the `soma_delete` preview, which 0.1.x returned
  unfenced.
- DNS-rebinding protection for the unauthenticated server (Host/Origin
  validation); the official conformance scenario failed before this release.
- With Auth0, `MCP_SINGLE_USER=1` and no allowlist, the server warns that every
  account of the Auth0 application gets full access.
- GitHub Actions are pinned to full commit SHAs, workflows default to
  `contents: read`; only the release's publish job can write, and it runs no
  third-party Python. Release tags must be annotated and on `main`. The build
  job runs only a hash-pinned build front end and backend and hashes the
  artifacts at once; in the release run, the wheel's dependencies run only in
  read-only jobs (a separate smoke job and the CI jobs, which never handle the
  release artifacts). Publish checks the exact file set against those digests,
  validates the smoke output and the release state before it attests, writes
  the notes from trusted job outputs, and publishes a draft release last. The
  wheel is reproducible from the tag with the recipe in
  [`RELEASE.md`](RELEASE.md) (§9), and CI checks that on every pull request.
- The conformance suites are installed from a lockfile
  (`tools/conformance/package-lock.json`, `npm ci --ignore-scripts`).
- The server refuses to start when the token store directory belongs to an
  account other than the service user or root, or is writable by group or
  others and cannot be restricted to mode 0700.
- CI fails on known vulnerabilities in the runtime dependency set and the
  declared floors (pip-audit, also weekly) and on committed secrets (gitleaks).

### Documentation

- README rewritten around what SOMA MCP is and is not, the supported stack,
  a quick start that was executed from scratch, and the security model.
- All documents describe this repository after the upgrade: protocol
  2026-07-28, FastMCP 4 (`github.com/PrefectHQ/fastmcp`), MCP SDK 2 client
  examples (`from mcp import Client`), the actual tool parameter names, and
  the encrypted `FileTreeStore`.
- Private deployment details (hostnames, container topology, deployment
  scripts that do not exist in this repository) were replaced by generic
  guidance; `docs/architecture.md` separates this repository's release process
  from any private production deployment.
- New: [`CHANGELOG.md`](CHANGELOG.md), [`RELEASE.md`](RELEASE.md),
  [`docs/upgrading.md`](docs/upgrading.md),
  [ADR-003](docs/adr/003-mcp-sdk-v2-fastmcp4-upgrade.md).

[Unreleased]: https://github.com/odbgrowth/soma-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/odbgrowth/soma-mcp/releases/tag/v0.2.0
