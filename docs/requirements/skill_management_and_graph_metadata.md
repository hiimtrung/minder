# Requirements: Skill Catalog Dashboard and Metadata-Only Graph Intelligence

**Date**: 2026-04-15
**Status**: Proposed
**Author**: Architect

---

## Goal

Add first-class skill lifecycle management to the product and correct the current graph-analysis direction so repository intelligence remains efficient at scale.

This feature must:

- let admins import reusable skills from external Git repositories, including GitHub, GitLab, and other Git-compatible sources
- let admins create, read, update, and delete skills directly in the Dashboard
- keep the skill model workflow-aware so skills can be tagged, curated, and reused by step
- change `GraphNode` handling from source-heavy ingestion to metadata-first ingestion
- avoid sending full source files into Gemma 3/4 for graph analysis by default
- allow code excerpts only when they are durable, high-signal, and worth preserving long term

---

## Current Baseline

The current codebase already provides:

- a persisted skill store and memory layer
- seed-based skill import from a GitHub repository via script-driven flows
- dashboard infrastructure and admin APIs for operational management
- a graph store that can persist nodes and edges with JSON metadata
- repository scanning and relationship tracking foundations

The current codebase still has product and architecture gaps:

- skill import is treated as a seeding/bootstrap concern instead of an operator-managed product capability
- the Dashboard does not expose skill CRUD or external skill-source import flows
- the documented external-source path is GitHub-specific rather than provider-agnostic
- the graph/repository-intelligence direction can drift toward full-source ingestion into Gemma 3/4, which is expensive and low-efficiency for structural analysis
- `GraphNode` policy is not yet explicitly documented as metadata-first

---

## Users

| Role              | Need                                                                                                 |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| Platform Admin    | Needs to import and curate reusable skills without shell access or seed-script dependency.           |
| ML / RAG Engineer | Needs graph analysis to stay efficient by using structural metadata instead of full-source payloads. |
| Backend Engineer  | Needs explicit API and storage contracts for skill lifecycle and graph metadata.                     |
| Frontend Engineer | Needs a clear Dashboard surface and typed contracts for skill management workflows.                  |

---

## User Stories

### Story 1: Import Skills From External Git Repositories

**As a** Platform Admin  
**I want to** import skill packs from GitHub, GitLab, or another Git repository through the Dashboard  
**So that** skill onboarding does not depend on server-side scripts or direct filesystem access.

**Acceptance Criteria**:

```gherkin
Given an authenticated admin opens the Dashboard skill catalog
When the admin submits a Git repository URL and source path
Then the system validates the source
And imports supported skill documents into the skill catalog
And records source metadata such as provider, repo URL, ref, and path
And prevents duplicate imports from creating uncontrolled duplicates
```

### Story 2: Manage Skills Directly in the Dashboard

**As a** Platform Admin  
**I want to** create, edit, review, list, and delete skills in the Dashboard  
**So that** reusable guidance can be curated as a product asset rather than a hidden seed artifact.

**Acceptance Criteria**:

```gherkin
Given the admin is on the Dashboard skill catalog
When the admin creates or edits a skill
Then the skill supports title, content, language, tags, workflow-step labels, and quality metadata
And changes are immediately visible through the admin APIs and Dashboard list view
When the admin deletes an obsolete skill
Then the skill no longer appears in the catalog and is excluded from future recall flows
```

### Story 3: Keep GraphNode Metadata-First

**As an** ML / RAG Engineer  
**I want** graph construction to store structural metadata instead of full source code  
**So that** Gemma 3/4 is not forced to analyze large low-signal payloads for topology extraction.

**Acceptance Criteria**:

```gherkin
Given a repository scan or graph refresh runs
When GraphNode entries are created or updated
Then the graph stores metadata for files, functions, controllers, routes, message queues, producers, consumers, and dependency edges
And the graph does not store full file contents by default
And any optional code excerpt is short, durable, and explicitly classified as a reusable excerpt
```

### Story 4: Preserve Long-Term Knowledge Value

**As a** Backend Engineer  
**I want to** store only high-value code fragments when necessary  
**So that** the knowledge base favors durable patterns over noisy snapshots.

**Acceptance Criteria**:

```gherkin
Given a function or controller is scanned
When the system considers persisting source text
Then it stores only a bounded excerpt when the content captures a stable contract, pattern, or long-lived implementation rule
And temporary, repetitive, or low-signal code is excluded from the graph payload
```

---

## Scope

### In Scope

- provider-agnostic skill import from GitHub, GitLab, and generic Git repositories
- Dashboard skill catalog pages and admin APIs for CRUD operations
- source provenance for imported skills
- graph metadata contract for files, functions, controllers, routes, and message-queue flow
- optional reusable code excerpt policy with explicit size and durability rules
- documentation updates across requirements, design, architecture, and planning docs

### Out of Scope

- full synchronization with every provider-specific webhook model
- storing full repository source inside the graph store
- replacing the existing memory tools with skill tools in the same change
- automatic skill generation from workflow history beyond the existing Phase 5 learning direction

---

## Key Architectural Decisions Required

| Topic                     | Required Decision                                                                   |
| ------------------------- | ----------------------------------------------------------------------------------- |
| Skill import sources      | Treat external skill import as Git-provider-agnostic, not GitHub-only               |
| Skill management surface  | Expose skill CRUD and import flows through admin APIs and Dashboard UI              |
| Graph ingestion policy    | Persist metadata-first graph nodes and edges; do not persist full source by default |
| Optional source retention | Allow short reusable excerpts only when they have long-term instructional value     |
| Import execution model    | Run remote import as an auditable admin operation with provenance and deduplication |

---

## Integration Points

| System / Module                       | Dependency Type       | Notes                                                                                          |
| ------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------- |
| `src/dashboard/`                      | Dashboard surface     | New skill catalog pages and import workflows live here.                                        |
| `src/minder/presentation/http/admin/` | Presentation layer    | New admin endpoints expose skill CRUD, import, and graph refresh summaries.                    |
| `src/minder/application/admin/`       | Application layer     | Use cases orchestrate validation, provenance, deduplication, and job status.                   |
| `src/minder/models/skill.py`          | Domain/data contract  | Skill model must grow to carry provenance and workflow-step metadata.                          |
| `src/minder/models/graph.py`          | Graph schema          | GraphNode metadata must prioritize structure over raw source.                                  |
| `src/minder/tools/ingest.py`          | Import seam           | Existing git ingestion path is a natural foundation for provider-agnostic remote import.       |
| `src/minder/tools/repo_scanner.py`    | Graph extraction seam | Repository scanning should emit metadata-rich nodes and edges without full-source persistence. |

---

## Non-Functional Requirements

- **Efficiency**: Graph extraction should minimize token and storage cost by using structural metadata rather than full-source payloads.
- **Traceability**: Imported skills must retain source provenance and import history.
- **Curatability**: Admins must be able to correct, refine, or remove imported skills without code changes.
- **Durability**: Stored excerpts must favor stable patterns and contracts, not ephemeral implementation noise.
- **Tenant Safety**: Admin and data access paths must remain tenant-aware and scoped.

---

## Open Questions

- [ ] Should private GitHub/GitLab imports use stored credentials, personal access tokens, deploy keys, or a bring-your-own clone URL model?
- [ ] Should remote imports run synchronously for small repositories and asynchronously for larger sources, or always as background jobs?
- [ ] What maximum excerpt size should qualify as a reusable long-term snippet?
- [ ] Should the Dashboard support scheduled refresh of imported skill sources, or start with manual refresh only?

---

## Decisions Log

| Date       | Decision                                                 | Rationale                                                                                                                 |
| ---------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-15 | Treat skill import as a provider-agnostic Git capability | Product value is the skill content, not the hosting provider. GitHub-only wording is too narrow.                          |
| 2026-04-15 | Make skill lifecycle a Dashboard-managed capability      | Skill curation is an operator workflow and should not depend on scripts or direct server access.                          |
| 2026-04-15 | Keep GraphNode metadata-first                            | Structural analysis does not justify storing full source in the graph path, and doing so wastes model and storage budget. |
| 2026-04-15 | Store code only as bounded reusable excerpts             | Long-term knowledge quality is higher when only durable, high-signal snippets are retained.                               |
