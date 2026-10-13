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
python3 .devflows/run.py package
python tools/check_release.py --tag "vX.Y.Z"
```

`tools/check_release.py` fails unless the version is `MAJOR.MINOR.PATCH`, the tag
is exactly `v` + version, and `CHANGELOG.md` has a non-empty, dated
`## [X.Y.Z] - YYYY-MM-DD` section. Use the planned release date. If the tag is
created on a later day, leave the date: the GitHub Release records the exact
publication time, and correcting the changelog is not worth another pull
request and merge approval.

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

All ten jobs of [`ci.yml`](.github/workflows/ci.yml) on the PR's last commit,
by check name:

- `Quality (lint, types, release metadata)`
- `Python 3.10`, `Python 3.11`, `Python 3.12`, `Python 3.13`, `Python 3.14`
  (tests with the coverage gate)
- `Dependency floor (Python 3.10, lowest direct versions)`
- `Security (pip-audit, gitleaks)`
- `Package (build, twine, clean wheel)`
- `Integration (official MCP conformance suite)`

A red job is fixed, never skipped.

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
git fetch origin
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" && echo "HEAD is origin/main"
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
for that approval after the artifacts are built, checked and smoke-tested.

### If the release workflow fails after the tag is pushed

- **Transient failure** (runner loss, network, a registry outage): open the run
  and use **Re-run failed jobs**. What a failed run leaves behind is listed in
  §8; a re-run completes a draft.
- **A real failure that needs a code change** (a new pip-audit advisory, a
  broken test): leave the tag where it is, fix the problem in a normal pull
  request and release the next patch version (`X.Y.Z+1`). Do not move the tag.
  `X.Y.Z` never gets a GitHub Release, so in that pull request move its
  changelog entries into the `## [X.Y.Z+1]` section and leave one line under
  `## [X.Y.Z]`: "Tagged, not released; see X.Y.Z+1." The release notes'
  compare link then starts at the last published release, not at the failed
  tag (the workflow skips tags without a published release).
- **Delete an unreleased tag** only with Onno's explicit approval, and only if
  no GitHub Release (draft or published) exists for it:
  `git push origin --delete "vX.Y.Z"` (the tag ruleset must allow it for the
  approver). This only tidies the tag list: the version number stays used, so
  never re-create `vX.Y.Z`, on any commit; release `X.Y.Z+1` as above.

## 8. What the release workflow does

[`release.yml`](.github/workflows/release.yml), triggered by `v*.*.*`:

1. `verify`: runs the complete CI ([`ci.yml`](.github/workflows/ci.yml)) on
   the tagged commit;
2. `build` (read-only token): checks the tag is annotated, on `main` and equal
   to `v{__version__}`, and extracts the changelog section (with links pointing
   at the tag) and the previous published release on the same line of history
   (a tag without a published release is skipped). It installs only the
   hash-pinned build front end, pip included (`.github/requirements-build.txt`),
   builds with the hash-pinned backend (`.github/constraints-build-backend.txt` with
   `PIP_REQUIRE_HASHES=1`), `SOURCE_DATE_EPOCH` set to the commit time and
   umask 022, hashes the sdist and wheel at once (`SHA256SUMS`, also a job
   output) and uploads them. No runtime dependency of the package ever runs on
   this runner;
3. `smoke` (read-only token, its own runner): checks the downloaded artifacts
   against the build digests, runs `twine check --strict`, installs the wheel
   with its dependencies in a clean virtualenv, runs
   `tools/smoke_test.py --expect-version` and passes on the one
   `soma-mcp --version` line;
4. `publish` (environment `release`): checks the artifacts against the build
   digests again (exact file set). Before anything is recorded, it validates
   the format of the line from `smoke` and stops if the release is already
   published. Then it records a build-provenance attestation for both artifacts
   (`actions/attest`, stored on the repository, verifiable with
   `gh attestation verify`), assembles the notes from trusted job outputs (the
   changelog section and digests from `build`, the validated line from
   `smoke`), puts the three assets on a **draft** GitHub Release, checks the
   draft holds exactly the expected asset names, and publishes that draft by
   id.

A failed run publishes no release. It can leave behind:

- the `release-dist` workflow artifact, downloadable from the run (the
  repository is public) for the repository's artifact retention period;
- once `publish` is past its attest step, a build-provenance attestation of the
  built artifacts. On a public repository it is also written to the public
  Sigstore transparency log, which keeps it; a re-run adds another for the same
  digests;
- a draft release, which a re-run completes.

A published release is final: with immutable releases enabled its assets and
tag cannot change, so a re-run stops before attesting and the fix is a new
patch version.

Only `publish` can write (`contents: write`, `id-token: write`,
`attestations: write`), and it installs and runs no third-party Python. In a
release run the release artifacts are built only in `build` and installed with
their dependencies only in `smoke`. `verify`'s CI jobs also build and install
the package and run its dependencies, but never handle the release artifacts
(and upload no package artifact for a tag). Every job except `publish` has a
read-only token.

**Reproducibility.** The wheel is reproducible: rebuilt from the tag with the
recipe in §9, it has the same SHA-256 as the released one, and the CI `Package`
job checks this on every pull request. The recipe matters. The backend version
is written into the wheel, its timestamps come from `SOURCE_DATE_EPOCH`, and
the zip stores each file's mode, so running `python -m build` under umask 002
gives a different hash (the umask of the checkout does not matter). The
recipe's front end pins pip as well: the backend's hash only satisfies
`PIP_REQUIRE_HASHES` from pip 26.1 on. The sdist is not yet byte-for-byte
reproducible (archive metadata).

## 9. Post-release verification

```bash
VERSION=X.Y.Z
mkdir "/tmp/soma-mcp-$VERSION" && cd "/tmp/soma-mcp-$VERSION"
gh release download "v$VERSION" --repo odbgrowth/soma-mcp
sha256sum --check SHA256SUMS
for f in "soma_mcp-$VERSION-py3-none-any.whl" "soma_mcp-$VERSION.tar.gz"; do
  gh attestation verify "$f" --repo odbgrowth/soma-mcp \
    --signer-workflow odbgrowth/soma-mcp/.github/workflows/release.yml
done

python -m venv venv
venv/bin/pip install "soma_mcp-$VERSION-py3-none-any.whl"
venv/bin/soma-mcp --version
```

Check the release page: title, notes, the three assets (wheel, sdist and
`SHA256SUMS`), and that the stack line matches the changelog.

To rebuild the wheel yourself and compare it (Python 3.10 or newer, any pip:
the first install puts the pinned pip into the virtualenv; run from an empty
directory, in one shell):

```bash
VERSION=X.Y.Z
umask 022                      # file modes are part of the wheel; keep it for the build
git clone --quiet --branch "v$VERSION" https://github.com/odbgrowth/soma-mcp src
cd src
python3 -m venv ../build-env
../build-env/bin/python -m pip install --require-hashes --no-deps -r .github/requirements-build.txt
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" \
PIP_CONSTRAINT="$PWD/.github/constraints-build-backend.txt" PIP_REQUIRE_HASHES=1 \
  ../build-env/bin/python -m build --outdir rebuilt
sha256sum rebuilt/*.whl        # equals the wheel's line in the release's SHA256SUMS
```

## 10. Rollback

A published tag is history: do not delete or move it. Roll back by releasing.

- **Bad release, users not yet affected**: add a warning to the release notes
  where your settings allow it (immutable releases lock the assets and the tag),
  then fix forward with a patch release.
- **Users need the previous version now**: install the previous release's wheel
  from its GitHub Release, or straight from the previous tag:

  ```bash
  gh release download "v<previous>" --repo odbgrowth/soma-mcp --pattern '*.whl'
  pip install "soma-mcp[auth] @ git+https://github.com/odbgrowth/soma-mcp@v<previous>"
  ```

- **Back to 0.1.x** (before the first tagged release): 0.1.0 has no tag and no
  upper bounds on its dependencies, so a plain reinstall pulls in a protocol
  stack it does not support. Use the pinned command in
  [`docs/upgrading.md`](docs/upgrading.md#rollback-to-01x), which also covers the
  token store.
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

- runs only after the `publish` job and only from a `v*.*.*` tag;
- uses a dedicated GitHub environment (for example `pypi`) with Onno as required
  reviewer;
- has `id-token: write` and nothing else;
- publishes the exact artifacts this workflow attested, without rebuilding.

That job needs its own ADR and approval before it is added.

## Repository settings that code cannot enforce

Configure these in GitHub (Settings → Rules / Environments / Code security);
this repository cannot enforce them.

**`main` (configured 2026-10-13, ruleset "Main protection"):**

- Required status checks: the ten check names in §4 (source: GitHub Actions),
  with "require branches to be up to date". A pull request that renames, adds
  or removes a CI job updates this list in the same change window: a renamed
  job leaves every pull request waiting on a check that never reports. Pull
  requests required, unresolved review threads block the merge, force pushes
  and deletions blocked, no bypass actors.
- Required approvals: GitHub never lets a pull request's author approve it.
  While agents open pull requests under the repository owner's account, an
  approval count above zero blocks every such PR; the merge gate is then Onno's
  explicit approval in the conversation plus the draft → ready step
  (`AGENTS.md`). Raise the count once a second reviewer identity exists.

**Before the first tag:**

- `release` environment: Onno as required reviewer, deployment rule limited to
  tags matching `v*.*.*`. Without it GitHub creates the environment on first use
  with no protection, and the publish job runs without a second approval.
- Tag ruleset on `refs/tags/v*`: restrict creations, updates and deletions,
  with "Repository admin" as the only bypass.
- Immutable releases enabled, so published assets and tags cannot change.
- Dependabot security updates enabled (private vulnerability reporting and
  secret scanning with push protection are already on).
