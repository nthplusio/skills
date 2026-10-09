# Discover and confirm tickets

Use this before binding work owners to tickets. A ticket is the repository's
confirmed, stable work record for one independently verifiable outcome.

## Discover facts, then resolve choices

Read repository guidance, contribution docs, issue templates and representative
tickets through read-only tools. Identify the tracker, record type, stable-ID
convention, required fields and existing acceptance-criteria format. Inspect
existing owner assignments too. A conversation title is a clue, not proof of
its original ticket binding.

Reuse choices explicitly supplied by the user or retained in the restored run.
Otherwise ask one focused question at a time, offering the discovered convention
and a recommendation. Resolve only what remains unknown:

1. Which established tracker and record type should count as a ticket here?
   If none exists, offer a local Markdown ticket with a stable ID and confirm
   its location and ID convention before creating records.
2. Which ticket definition and layout should this run use? Prefer the
   repository's existing template. When it lacks one, propose the default below.
   Confirm the acceptance-criteria limit as part of that template choice.
3. For a ticket with an unclear outcome, scope or proof, ask the specific missing
   question before assigning it. Draft a proposed split when the ticket instead
   has independent outcomes or exceeds the confirmed criterion limit.

Record the confirmed repository, tracker/local source, definition/template,
criterion limit and actual confirmation source in the run record or restored
conversation. Keep repository choices separate from harness tool capabilities.
A suggested default or unanswered question remains a proposal. Continue work on
already defined tickets while affected definitions or splits await answers.

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
