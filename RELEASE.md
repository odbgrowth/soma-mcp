# Release runbook

How a SOMA MCP version goes from `main` to a tagged GitHub Release. Every
command is copy-paste ready. The release workflow does the building; humans do
the deciding.

**Authority.** Merging, tagging, publishing to a package index and deploying
each need a separate, explicit approval from Onno (see [`AGENTS.md`](AGENTS.md)).
An agent may prepare everything up to step 6 and must stop there.

**What a release is here.** A Git tag `vX.Y.Z`, a wheel and an sdist with
`SHA256SUMS` and a GitHub build-provenance attestation, attached to a GitHub
Release. Nothing is published to PyPI and nothing is deployed: this is the public
reference repository, not a production system.

## 0. Versions in play

Keep these apart in every note and changelog entry:

| What | Where it lives | Example |
|---|---|---|
| SOMA MCP package version | `src/soma_mcp/__init__.py` (`__version__`, the only source) | `0.2.0` |
| Release tag | Git, annotated | `v0.2.0` |
| FastMCP / MCP SDK compatibility | `pyproject.toml` dependency ranges | `fastmcp>=4.1,<5`, `mcp>=2.3,<3` |
| MCP protocol revision | negotiated by the MCP SDK; reported by `soma-mcp --version` | `2026-07-28` (+ handshake revisions) |

## 1. Choose the version

[Semantic Versioning](https://semver.org/). While the version is `0.y.z`:

- **minor** (`0.2.0` → `0.3.0`): protocol-stack majors (FastMCP, MCP SDK), a new
  MCP protocol revision, changed tool names, parameters or result shapes,
  changed configuration semantics, anything that needs `docs/upgrading.md`;
- **patch** (`0.2.0` → `0.2.1`): fixes, dependency floor bumps for security,
  documentation, CI.

`1.0.0` is a deliberate decision to declare the public API (`Engine`,
`InMemoryEngine`, `Kernel`, `build_server`, `main`, the tool surface) stable. It
is never the side effect of a routine release.

Pre-release versions (`rc`, `a`, `b`) are not supported by the tooling; the
release workflow only accepts `vMAJOR.MINOR.PATCH`.

## 2. Prepare the release pull request

On a feature branch, never on `main`:

```bash
# 1. bump the single version source
$EDITOR src/soma_mcp/__init__.py            # __version__ = "X.Y.Z"

# 2. move [Unreleased] entries into a dated section
$EDITOR CHANGELOG.md                        # ## [X.Y.Z] - YYYY-MM-DD
                                            # + the [X.Y.Z] compare link at the bottom

# 3. upgrade notes, if anything changes for operators or clients
$EDITOR docs/upgrading.md

# 4. local gates (same as CI)
.devflows/verify
.devflows/run.py package
python tools/check_release.py --tag "vX.Y.Z"
```

`tools/check_release.py` fails unless the version is `MAJOR.MINOR.PATCH`, the tag
is exactly `v` + version, and `CHANGELOG.md` has a non-empty, dated
`## [X.Y.Z] - YYYY-MM-DD` section. Use the planned tag date; if the tag slips to
another day, correct the date in a follow-up commit before tagging.

## 3. Reviews

Open the PR as a draft and fill in the template. Before it is marked ready:

1. **Independent review**: the Codex `reviewer` role
   (`.codex/agents/reviewer.toml`) or another reviewer who did not write the
   change. Findings are ordered P0 to P3; P0/P1 block the release.
2. **Security review** (`.codex/agents/security.toml`) for anything touching
   auth, token storage, allowlists, dependencies, CI permissions or the release
   path. P0/P1 block the release.
3. **Release readiness** (`.codex/agents/devops.toml`): CI, artifacts, rollback.

## 4. CI must be green

All jobs of [`ci.yml`](.github/workflows/ci.yml) on the PR's last commit:
quality, tests on Python 3.10 to 3.14 (with the coverage gate), dependency floor,
security (pip-audit, gitleaks), package (build, `twine check`, clean-wheel smoke
test) and the MCP conformance job. A red job is fixed, never skipped.

**Coverage.** The threshold in `pyproject.toml` (`fail_under`) only moves up. A
PR that lowers it states why in its description and needs explicit approval.

## 5. Merge (Onno approval required)

Squash or merge per the repository settings once approved. Then update your
local `main`:

```bash
git switch main
git pull --ff-only origin main
git log -1 --oneline   # the release commit
```

## 6. Final local check on `main`

```bash
python tools/check_release.py --tag "vX.Y.Z"
git status --short     # must be empty
```

An agent stops here and reports the exact tag command for Onno.

## 7. Tag (Onno approval required)

Annotated tags only; the release workflow rejects lightweight tags.

```bash
VERSION=X.Y.Z
git tag -a "v$VERSION" -m "SOMA MCP $VERSION"
git push origin "v$VERSION"
```

Never move or reuse a published tag. Never use `latest`, `prod` or
`release-*` as release tags. The workflow rejects a tag whose commit is not on
`main`.

Human gate (required before the first release, see "Repository settings"): the
`release` environment has Onno as required reviewer, so the publish job waits
for that approval after the artifacts are built and verified.

## 8. What the release workflow does

[`release.yml`](.github/workflows/release.yml), triggered by `v*.*.*`:

1. `verify`: runs the complete CI ([`ci.yml`](.github/workflows/ci.yml)) on
   the tagged commit;
2. `build` (read-only token): checks the tag is annotated, on `main` and equal
   to `v{__version__}`, extracts the changelog section, builds the sdist and
   wheel, runs `twine check --strict`, installs the wheel in a clean virtualenv
   and runs `tools/smoke_test.py --expect-version`, writes `SHA256SUMS` and the
   release notes, and uploads them as workflow artifacts;
3. `publish` (environment `release`): downloads the artifacts, verifies
   `SHA256SUMS`, creates a build-provenance attestation for both artifacts
   (`actions/attest`), and creates the GitHub Release (or updates it on a
   re-run) with the changelog section, the exact stack line, the checksums and
   verification commands.

Only `publish` can write (`contents: write`, `id-token: write`,
`attestations: write`), and it installs and runs no third-party Python: build
backends, CI tools and the wheel's dependencies only ever run with a read-only
token.

## 9. Post-release verification

```bash
VERSION=X.Y.Z
mkdir "/tmp/soma-mcp-$VERSION" && cd "/tmp/soma-mcp-$VERSION"
gh release download "v$VERSION" --repo odbgrowth/soma-mcp
sha256sum --check SHA256SUMS
gh attestation verify "soma_mcp-$VERSION-py3-none-any.whl" --repo odbgrowth/soma-mcp

python -m venv venv
venv/bin/pip install "soma_mcp-$VERSION-py3-none-any.whl"
venv/bin/soma-mcp --version
```

Check the release page: title, notes, the three assets (wheel, sdist and
`SHA256SUMS`), and that the stack line matches the changelog.

## 10. Rollback

A published tag is history: do not delete or move it. Roll back by releasing.

- **Bad release, users not yet affected**: mark the GitHub Release as a
  pre-release or edit its notes with a warning, then fix forward with a patch
  release.
- **Users need the previous version now**: install the previous release's wheel
  from its GitHub Release (`gh release download v<previous>`), or pin
  `soma-mcp==<previous>` from a Git URL at the previous tag.
- **Dependency regression** (a new FastMCP or MCP SDK minor inside the range
  breaks something): release a patch that tightens the range, for example
  `fastmcp>=4.1,<4.3`, then fix forward.
- **OAuth token storage** (0.2.0 moved from `DiskStore` to an encrypted
  `FileTreeStore`): rolling back to 0.1.x means connectors register once more
  against an empty store. Never restore or copy an old `mcp_tokens/` DiskStore
  directory from a backup: it is pickle-based and loading untrusted content from
  it executes code (CVE-2025-69872). See [`docs/upgrading.md`](docs/upgrading.md).

## 11. Optional future step: PyPI

Not enabled. If SOMA MCP is ever published to PyPI, do it with
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no
long-lived API token) from a separate job that:

- runs only after the release job and only from a `v*.*.*` tag;
- uses a dedicated GitHub environment (for example `pypi`) with Onno as required
  reviewer;
- has `id-token: write` and nothing else;
- publishes the exact artifacts this workflow attested, without rebuilding.

That job needs its own ADR and approval before it is added.

## Repository settings that code cannot enforce

Configure these in GitHub (Settings → Rules / Branches / Environments /
Code security) **before the first tag**; this repository cannot enforce them:

- `main`: pull request required, required status checks = every job in
  `ci.yml`, branches up to date before merging, at least one independent
  approval, no force pushes, no deletions, no direct pushes (admins included).
- Tag ruleset on `refs/tags/v*`: only maintainers may create; no updates or
  deletions.
- `release` environment: required reviewer (Onno), deployment rule limited to
  tags `v*.*.*`.
- Immutable releases enabled, so published assets cannot be replaced.
- Private vulnerability reporting, secret scanning with push protection, and
  Dependabot security updates enabled under **Settings → Code security**.
