# 04. Workflow Governance

## Goal

Minder must support configurable engineering processes so the primary LLM does not behave as a free-form assistant only. It must behave as a process-aware agent guided by company policy.

## Example TDD Workflow

```text
Problem Intake
  -> Problem Analysis
  -> Use Case Definition
  -> Test Writing
  -> Implementation
  -> Verification
  -> Review
  -> Release
```

## Expected Behavior

Once a workflow is configured, Minder must:

- Tell the LLM the active workflow and current step
- Tell the LLM which artifacts are required for the current step
- Block or warn when the LLM tries to skip mandatory steps
- Persist workflow state per repository
- Persist repository-specific context inside that repository
- Read repository state back into context for future sessions
- Suggest the next valid step after each completed step
- Track step completion and relationships between artifacts
- Maintain a compact continuity brief so long-running flows survive context-window limits
- Use local Gemma 4 synthesis to clarify unresolved issues, assumptions, and next actions

## Long-Flow Continuity Process

For large flows, Minder should run a continuity loop at each major transition:

1. Collect the current workflow state, session state, and top memory candidates.
2. Synthesize a short continuity brief with Gemma 4 local.
3. Validate suggested next actions against workflow gates and required artifacts.
4. Persist the brief to session state and memory metadata.
5. Inject the brief into the next primary LLM prompt with token budgeting.

The loop must prioritize deterministic process constraints first, then free-form suggestions.

## Continuity Brief Requirements

Each generated brief should contain:

- current problem framing
- confirmed progress and completed artifacts
- unresolved blockers and open questions
- risk and confidence signals
- next valid actions (ordered, process-compliant)
- source references (session/memory artifact IDs)

This keeps the primary LLM grounded when the original conversation exceeds effective context windows.

## Repository-Local State Requirement

Each repository should contain a local state area managed by Minder, for example:

```text
.minder/
  workflow.json
  context.json
  relationships.json
  artifacts/
    use-cases.json
    test-plan.json
    review-notes.json
```

This repository-local state allows:

- Portable workflow progress per repository
- Better context restoration across sessions
- Repository-specific guidance for the LLM
- Transparent auditability for teams
- Easier collaboration across contributors

## Dashboard Requirement

Minder should expose a dashboard to let teams:

- Define workflows and step order
- Configure mandatory and optional gates
- Assign rules by repository or repository group
- Inspect repository state and step progress
- Review blocked items and missing prerequisites
- Manage users, API keys, and roles
- View metrics, audit logs, and CI/CD status
