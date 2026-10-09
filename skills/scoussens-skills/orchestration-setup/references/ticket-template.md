# Confirm ticket policy and prepare splits

Setup uses the policy section. Run uses the confirmed policy, default layout
when selected, and split rules. A ticket is the repository's
confirmed, stable work record for one independently verifiable outcome.

## Confirm project policy in setup

Read saved discovery's repository conventions. Retrieve referenced guidance,
templates, or representative tickets when needed to settle a preference.
Discovery owns facts about the tracker, record type, stable IDs, required fields,
and existing acceptance-criteria format.

Reuse choices explicitly supplied by the user or already confirmed in setup.
Otherwise ask one focused question at a time, offering the discovered convention
and a recommendation. Resolve only what remains unknown:

1. Which established tracker and record type should count as a ticket here?
   If none exists, offer a local Markdown ticket with a stable ID and confirm
   its location and ID convention before creating records.
2. Which ticket definition and layout should this project use? Prefer the
   repository's existing template. When it lacks one, propose the default below.
   Confirm the acceptance-criteria limit as part of that template choice.

Record the confirmed repository, tracker/local source, definition/template,
criterion limit, and actual confirmation source in `project.ticket_policy`.
Keep repository choices separate from harness capabilities. A suggested default
or unanswered question remains a proposal.

During a run, use that policy without another project interview. For a ticket
with an unclear outcome, scope, or proof, resolve that ticket's missing choice
before assignment. Continue unrelated tickets while affected definitions or
splits await answers. Inspect original owner assignments before reuse. A
conversation title is a clue, not proof of its original ticket binding.

## Default ticket layout

Propose this only when the repository has no established layout. Use one outcome
and one to five observable acceptance criteria. Five is the default maximum,
not permission to override a confirmed repository policy. Keep implementation
steps and repeated assertions out of acceptance criteria.

```markdown
# <stable ID>: <short outcome title>

## Outcome
<One user-visible or operational result.>

## Scope
<Included work and file/runtime boundaries.>
Excluded: <What this ticket does not change.>

## Acceptance criteria
1. <Observable result with an input/condition and expected outcome.>
2. <Another necessary result, if any. At most five criteria total.>

## Dependencies
<Blocking ticket IDs or external decisions, or None.>

## Required proof and finish line
<Checks/artifacts that prove the criteria, plus the requested delivery milestone.>
<Name any shared actions requiring separate authorization.>
```

For example, a persistence criterion can say "After a successful save, reopening
the record shows the edited value." Its proof should exercise save and reopen;
"add a save helper" is an implementation step, not an acceptance criterion.

## Split proposals are not tracker writes

When a ticket has independent outcomes or too many criteria, preserve the
original and draft smaller child tickets in the confirmed format. Carry every
required outcome into a child, name dependencies, and give each child its own
finish line and proof. Label identifiers as proposed until the tracker actually
assigns them. Keep the parent as the reference for the proposed split rather
than assigning its overlapping implementation to another owner.

Show the proposed split and obtain approval before binding new owners to its
children. Create or update shared tracker records only within explicit tracker-
write authorization. Local draft permission is not shared publication permission.
After approval, each child gets one persistent owner. A bounded helper can assist
within a child's assignment without becoming another ticket owner.
