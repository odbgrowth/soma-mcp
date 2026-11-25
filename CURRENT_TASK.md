# Current task

## Keep the announced surface fixed on FastMCP 4.2.5

This file does not authorize commit, push, merge, environment sync, tagging or
deployment.

- **Goal and scope:** `main` passes every check on FastMCP 4.2.5 with an unchanged
  documented surface: `build_server` switches `enable_subscriptions_listen` off while the
  server is created (and restores it), also against `FASTMCP_ENABLE_SUBSCRIPTIONS_LISTEN=true`,
  plus a test that fails without it. No release, no version bump, no dependency change.
- **Owner role and provider:** developer (Claude Code), with an independent
  reviewer pass before the PR leaves draft.
- **Branch/worktree:** `claude-clients/zealous-goldberg-9r4ou5` (assigned by the
  session), draft PR against `main`.
- **Validation evidence:** `.devflows/verify`, the conformance suite and the CI checks;
  see the PR.
- **Risks/unknowns:** FastMCP 4.1 has no such setting, so the code does nothing there.
- **Next action and required approval:** push and draft PR after the guarded
  confirmation; merge needs a separate approval.

## Delivery boundary

- New work starts from `main` through the project launcher and an isolated worktree.
- Architecture requires an ADR plus explicit Onno approval.
- Commit, push, and draft PR require guarded confirmation.
- Merge, production environment changes, deployment, and rollback each require a new,
  exact Onno approval.
