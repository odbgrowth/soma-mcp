# Current task

## Make the documentation match the code and a running server

This file does not authorize commit, push, merge, environment sync, tagging or
deployment.

- **Goal and scope:** every statement in the current documents (`README.md`,
  `RELEASE.md`, `docs/`) holds against the code, the workflows and a server
  running on the supported FastMCP range. Documentation and one script comment
  only: no code, no test, no dependency, no release, no version bump.
- **Owner role and provider:** developer (Claude Code), with an independent
  reviewer pass before the PR leaves draft.
- **Branch/worktree:** `claude/epic-euler-mmubba` (assigned by the session),
  draft PR against `main`.
- **Validation evidence:** `.devflows/verify` (the documentation tests included),
  a wire probe against a local server on both protocol eras, and the same tool
  listing on the FastMCP floor (4.1.2) and on 4.2.6; see the PR.
- **Risks/unknowns:** two statements describe third-party products as observed
  in November 2026 and age with them: the MCP Inspector's Node requirement and
  the unique app name in ChatGPT.
- **Next action and required approval:** draft PR; merge needs a separate
  approval.

## Delivery boundary

- New work starts from `main` through the project launcher and an isolated worktree.
- Architecture requires an ADR plus explicit Onno approval.
- Commit, push, and draft PR require guarded confirmation.
- Merge, production environment changes, deployment, and rollback each require a new,
  exact Onno approval.
