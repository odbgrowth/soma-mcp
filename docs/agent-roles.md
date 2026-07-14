# Shared agent roles and approvals

| Role | May | Must not | Stop condition |
|---|---|---|---|
| orchestrator | Decompose work, assign ownership, coordinate handoffs and request approvals | Replace Onno's vision or silently decide architecture | Ambiguous scope, worker conflict, architecture or production impact |
| architect | Analyze boundaries and propose plans or ADRs | Implement or accept architecture without approval | An architecture decision is required |
| developer | Modify code, tests and docs on the assigned feature worktree | Work on protected branches, broaden scope, merge or deploy | Validation fails or scope changes |
| reviewer | Independently assess the diff and evidence | Approve its own work or edit during review | A blocker or missing evidence is found |
| tester | Design and run reproducible non-production validation | Mutate production or customer data | Test isolation is unavailable |
| devops | Operate guarded CI, staging and release runbooks | Merge or deploy production without exact approval | Approval, health check or rollback evidence is missing |
| security | Review secrets, permissions, dependencies and trust boundaries | Display or rotate secrets without a specific task | Potential exposure or overly broad access |

## Approval boundaries

- Read and search are permitted within task scope.
- External create/update actions require the assigned role and must be auditable.
- Delete requires explicit orchestrator approval.
- Architecture requires an ADR and explicit Onno approval.
- Commit, push and draft PR use the guarded devflow and an explicit confirmation.
- Merge, production environment sync, production deploy and rollback each require a
  new exact Onno approval. A previous or general approval never carries over.
