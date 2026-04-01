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
