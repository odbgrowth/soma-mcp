# Current task

## Close three findings from the November 2026 security review

This file does not authorize commit, push, merge, environment sync, tagging or
deployment.

- **Goal and scope:** three small fixes, each with a test that fails without it:
  single-user mode no longer opens a missing write allowlist next to a
  configured access allowlist ([ADR-004](docs/adr/004-single-user-mode-and-allowlists.md));
  the documented attestation check binds to the release tag; the audit log uses
  the shared data directory, reports a failed write and creates its file
  owner-only. No release, no version bump, no deployment.
- **Owner role and provider:** developer (Claude Code), with an independent
  reviewer pass before the PR leaves draft.
- **Branch/worktree:** `claude-clients/zealous-goldberg-9r4ou5` (assigned by the
  session), draft PR against `main`.
- **Validation evidence:** `.devflows/verify` and the ten CI checks; see the PR.
- **Risks/unknowns:** operators who combined single-user mode with an access
  allowlist and no write allowlist lose write access after upgrading
  (`CHANGELOG.md`).
- **Next action and required approval:** push and draft PR after the guarded
  confirmation; merge needs a separate approval.

## Delivery boundary

- New work starts from `main` through the project launcher and an isolated worktree.
- Architecture requires an ADR plus explicit Onno approval.
- Commit, push, and draft PR require guarded confirmation.
- Merge, production environment changes, deployment, and rollback each require a new,
  exact Onno approval.
