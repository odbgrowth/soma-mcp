# Current task

## Modernize the MCP stack and the release pipeline (0.2.0)

This file does not authorize commit, push, merge, environment sync, tagging or
deployment.

- **Goal and scope:** move SOMA MCP to FastMCP 4 / MCP Python SDK 2 / protocol
  2026-07-28; replace the pickle-based OAuth `DiskStore`; fail-closed
  configuration; one version source; CI (lint, types, Python 3.10 to 3.14,
  dependency floor, pip-audit, gitleaks, package, conformance); tag-driven
  release workflow; documentation refresh. No production deployment, no PyPI.
- **Owner role and provider:** developer (Claude Code), with independent
  reviewer, security and devops passes before the PR leaves draft.
- **Branch/worktree:** `claude-clients/exciting-faraday-q6gn4k` (assigned by the
  session), draft PR against `main`.
- **Decisions and current state:** [ADR-003](docs/adr/003-mcp-sdk-v2-fastmcp4-upgrade.md),
  accepted by Onno on 2026-10-13, who also approved the merge. Implementation,
  tests, documentation, reviews and CI are complete; see the PR.
- **Files changed:** see the PR; summary in [`CHANGELOG.md`](CHANGELOG.md) under 0.2.0.
- **Validation evidence:** `.devflows/verify`, `python3 .devflows/run.py package`,
  `tools/run_conformance.sh`, the ten CI checks (quality, the Python 3.10 to
  3.14 matrix, dependency floor, security, package with the reproducible-wheel
  check, conformance) and the review results; all in the PR description.
- **Risks/unknowns:** clients re-register once (new token store); unauthenticated
  servers now bind to loopback; GitHub branch, tag and environment protection
  must be configured by hand (RELEASE.md).
- **Next action and required approval:** before the tag, Onno configures the `release` environment, the tag ruleset, immutable
  releases and Dependabot security updates (RELEASE.md, "Repository
  settings"), then approves and creates the annotated tag `v0.2.0`
  (RELEASE.md, step 7).

## Delivery boundary

- New work starts from `main` through the project launcher and an isolated worktree.
- Architecture requires an ADR plus explicit Onno approval.
- Commit, push, and draft PR require guarded confirmation.
- Merge, production environment changes, deployment, and rollback each require a new,
  exact Onno approval.
