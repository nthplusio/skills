# Answering questions before they reach the owner

The owner's time is the scarcest resource on the project. A question reaches
the owner only after the sources have been checked and could not settle it.

## The source ladder

The owner sets the sources and their order once, and the record states them
under **How open questions get answered**. Ask the owner for the ladder when
the record does not have one yet. A typical ladder is:

1. Meeting recordings and transcripts, such as Thenact or Wispr Flow. These
   carry the decisions people actually made.
2. The design reference: a prototype, mockups, or a spec app.
3. The existing applications' code.
4. When necessary: the databases, **read only** and SELECT-only.

Never ask other people directly unless the owner's rule allows it. When the
owner says a person is no longer asked, record the rule with its date.

## Route each question

1. **The editor can decide it:** the question is reversible and in scope,
   and choosing either way does not change what the owner asked for. Decide
   it, act on it, and record it as `(decided by me, YYYY-MM-DD)` under
   **Answered by research**, with why it is reversible.
2. **Otherwise, research it.** Start one research thread or subagent per
   question, with read-only access, using the brief below. Use a
   high-reasoning mode when the harness offers one.
3. **The sources settle it:** record the answer under **Answered by
   research**, labelled `(research, YYYY-MM-DD)`, with its citations. It is
   open to the owner's veto. Send the answer to the lanes it affects.
4. **The sources do not settle it:** add a decision item under
   **Needs \<Owner>** with the research's recommendation, the sources checked,
   and what it is holding up. A question goes to the owner even when research
   could not recommend anything; say so in Recommendation.

Several questions can be researched at once. Track each research thread in
**Lane work** or in the item's Sources line until it reports.

## Research brief

Give each research thread this brief, filled in:

```text
Question: <the question, in plain words>
Context: <what exists today and why it is a question; links to the record item>
Sources, in this order: <the ladder, with the specific meetings, files, apps,
  or tables to start from>
Rules: read only. SELECT-only queries. Do not contact anyone. Do not edit the
  record or any branch.
Reply with send_thread_message to <editor thread ID> (or as your final
  message), containing:
  - the question
  - the recommendation, outcome first
  - why, and the tradeoff it accepts
  - citations: file:line; meeting, timestamp or cue, and a short quote; or the
    query and its counts
  - confidence: settled by a source, or a judgment
  - if no source settles it: exactly what the owner must decide, with the
    options
```

## Turning a research reply into a record entry

- Copy citations exactly. Do not upgrade "a judgment" to "settled".
- Write the decision item for the owner, not for the researcher. Remove
  jargon, give the outcome first, and keep the detail in nested bullets.
- When research changes an earlier recommendation, say so: "Changed after the
  full transcript: …".
