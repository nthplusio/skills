# Discovering the contract

Discover only what the assignment needs. Keep the mapping in working context;
do not create a ticket-standards document, configuration file, shadow backlog,
or copied policy in the consuming repository.

## Find the authoritative sources

1. Read applicable repository and user instructions, including `AGENTS.md` or
   `CLAUDE.md`, and follow their pointers to contribution and ticketing standards.
2. Inspect the relevant issue templates, tracker configuration, workflow
   automation, and documented definition of done. Paths vary; examples include
   `.github/ISSUE_TEMPLATE/`, `CONTRIBUTING.md`, and a repository's local issues
   directory. These are places to inspect, not files to create.
3. Read the connected tracker project's live workflow, required fields, label
   taxonomy, relation types, permissions, and automation where accessible. A
   GitHub issue's open/closed state may coexist with a Projects status; a Jira
   workflow may require an explicit transition; a local tracker may use files
   and frontmatter. Discover supported operations through tool schemas or CLI
   help rather than guessing field names or IDs.
4. Read representative recent tickets only for gaps left by explicit guidance.
   Examples show practice, not authority to override a documented rule.
5. If saved discovery points to these sources, use the pointers and verify the
   facts needed for a write against live state. Reuse established discovery
   storage only when its owning workflow requires it; this skill needs no cache.

Respect instruction precedence. Within that boundary, use the most specific
applicable documented rule; live tracker capabilities determine which actions
are possible. If a document requires a transition the tracker cannot perform,
report the mismatch rather than inventing a mapping. For a material conflict
without a clear authority, hold only the affected write and ask a focused
question. Work that does not depend on that decision can continue.

## Resolve these facts

| Fact | What to establish |
| --- | --- |
| Identity | Canonical tracker URL or local path, repository/project, ticket ID and type. |
| Scope | Outcome, acceptance criteria, parent/children, dependencies, explicit exclusions. |
| Presentation | Title style, required body sections, where plans and evidence belong. |
| Lifecycle | Start, blocked, review, and completion transitions; automation-owned changes and definition of done. |
| Classification | Allowed labels/tags/components/types, required combinations, ownership and priority rules. |
| Access | Available tools, read/write permissions, known actor identity, required approvals. |

Absence is a valid result. If no convention is discoverable, preserve the ticket's
structure and semantics, make only evidence-backed clarity edits, use available
native states, and leave unknown classification alone. Use a short comment for
a meaningful status the tracker cannot represent. Ask only when a missing fact
blocks correct execution or a required write. Do not bootstrap a new ticketing
standard, create taxonomy, or install a tracker as part of routine hygiene.

## Maintain one source of truth

Use native relationships for parentage and blockers where available. If the
repository uses a canonical checklist or file links instead, maintain those.
Keep the parent plan in the established plan field, body section, or linked
planning document. Child tickets own their detailed progress and acceptance
evidence. Parent plans link to them; they do not mirror their bodies or logs.

These bundled references describe discovery and execution, not repository
policy. If a repository has its own comment template, state names, or tagging
rules, read those at their source rather than copying them into this skill.
