# Working a parent

Own the whole assigned outcome, not just the first child that looks executable.
Planning child work is part of the assignment; delegation is optional and must
follow the active environment's rules.

## Plan every child before implementation

1. Enumerate all children, following pagination and nested parents. Read their
   acceptance criteria, state, ownership, dependencies, and completion evidence.
   Keep completed and cancelled children visible in reconciliation; do not
   reopen them merely to make the plan uniform.
2. Compare the descendants with the parent's acceptance criteria. Reuse tickets
   that cover the work. If a required piece is missing, create the smallest
   useful child under the repository's rules and permitted authority, then
   confirm its relationship. Search first and read back after uncertain writes
   so retries do not create duplicates. Leave unrelated follow-ups outside the
   assigned scope.
3. Establish dependency edges from documented requirements and implementation
   constraints. Distinguish a blocking dependency from a related ticket. If a
   cycle or unknown dependency prevents ordering, record the specific gap and
   resolve it before the affected work starts.
4. Put one concise plan in the repository's canonical planning location. For
   each child, link its canonical record, name its contribution to the outcome,
   prerequisites, completion check, and next owner/action. Order by dependencies;
   group independent children only when parallel execution is supported and safe.
   Link a nested parent's plan rather than duplicating its full detail.

**Planned when** every descendant is accounted for, every parent acceptance
criterion maps to work or verified evidence, missing children are created or
explicitly gated, and the next executable children are identifiable.

## Execute the plan, not just a sample

Apply the main skill's ownership, cleanup, tagging, comments, status changes,
and verification to each child as it starts. For a nested parent, repeat this
planning process and work its descendants. Keep unrelated workers' ownership
and changes intact.

Work ready children in dependency order. Treat a prerequisite as satisfied only
at the gate its dependent needs: merged code is not a deployed service. If a
child blocks, update that child and the parent's aggregate impact, then work
other independent children. For human-owned work, name the needed action and
owner; do not impersonate completion. If all remaining work is blocked or
approval-gated, leave an accurate plan and state instead of claiming success.

When delegation is permitted, give each worker the canonical ticket, source
pointers for repository standards, acceptance criteria, dependency constraints,
and the requirement to apply this skill. Establish one writer per ticket to
avoid competing body and status updates. The coordinator owns the parent;
child owners update their child. Read the actual ticket and work evidence before
accepting a worker's completion claim.

After a child reaches its completion gate, update its canonical checklist and
relations as required, then advance ready dependents. Keep the parent plan's
progress concise; link child evidence instead of duplicating it. Refresh child
relationships at milestones to catch newly added or re-scoped work.

**Executed when** every in-scope unfinished descendant is either worked through
its required gate or has a recorded blocker, next owner, and unblock condition.

## Reconcile before parent completion

Read the live descendants and verify the parent's outcome, including integration
checks that no individual child covers. Open review, missing delivery evidence,
blocked descendants, and unresolved acceptance criteria keep the parent open
under its workflow. If a child was cancelled or moved out of scope, cite the
authorized decision and reconcile its contribution to the parent outcome;
cancellation alone is not proof that an acceptance criterion is met.

Close the parent only at its own documented completion gate. Otherwise record
what is delivered, what remains, and who can advance it. A summary or plan is
not completion of the assigned children.
