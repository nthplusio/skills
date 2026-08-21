# Writing the items

The voice a stakeholder brief needs, and the traps that break trust.

## Contents

- [Lead with the observable effect](#lead-with-the-observable-effect)
- [Describing a security fix](#describing-a-security-fix)
- [Counts you can defend](#counts-you-can-defend)
- [The framing conversation](#the-framing-conversation)
- [Foundation work](#foundation-work)
- [Words to cut](#words-to-cut)

## Lead with the observable effect

Open each item with what a person using the product would notice, then explain
in one or two sentences, then reference. The heading carries the whole item for
a reader who skims, so it has to survive being read alone.

| Instead of | Write |
| --- | --- |
| Fixed upsert to scope field writes | Re-importing the roster no longer erases what staff wrote |
| Added RBAC guard to upload session mutation | Only staff can upload study materials |
| Resolved render loop in season wizard | Season Setup no longer crashes |
| Corrected recurrence weekday calculation | A season's meetings land on the group's actual meeting day |
| Migrated notes column to Adult model | A person's record now lives in exactly one place |

Two habits make the difference. Name the surface the reader knows — *the roster
import*, *Season Setup* — rather than the module you changed. And describe the
world after the fix, not the operation you performed on the code.

When a fix is hard to feel, say what it prevents: *a stale copy could hide a
real family from the People list*. Consequence is the bridge from a schema
change to something a stakeholder can weigh.

## Describing a security fix

A stakeholder reads a security item twice as carefully as any other, so it has
to be accurate in both directions. Overstating invites a crisis that is not
happening; understating is worse.

State what was possible, who could do it, and what closed it:

> Any signed-in account — including an ordinary member — could ask the system
> for permission to write files into the study-materials store. Requesting that
> permission now requires a staff role.

On exploitation, claim only what you checked. "Neither is known to have been
exploited" is fair when the tracker records no incident, and it is worth
telling the user that this is the sentence a reader is most likely to ask a
follow-up about — they may have audit-log evidence you do not.

Never name an unfixed weakness in a document that will be forwarded.

## Counts you can defend

A summary figure invites arithmetic, so make each one survive it.

- Count what you can name. If the page lists 25 items, the figure is 25.
- **Watch the verb.** *Closed* is a tracker state; *shipped* is a deployment
  fact. They diverge whenever a fix is released while its issue stays open for
  the reporter to confirm. Pick the verb the number actually supports, and
  footnote the exception rather than rounding it away.
- State the window beside the figure. "34 pull requests" means nothing without
  "merged Monday 17 to Friday 21".
- Prefer figures you can rebuild from the same command twice.
- Do not report a metric you did not measure. *Zero regressions* requires
  evidence, not the absence of a report.

## The framing conversation

The same set of changes usually supports several honest stories: guardianship
of customer data, removing friction from the work, or evidence of steady
delivery. Which one leads is the user's call, and it is worth a moment of theirs
because it reorders the entire page.

Offer two or three framings, each with the section order it implies, and say
which you would pick. Ground every option in the work — a framing the items do
not support is not an option, however much the user might like it.

## Foundation work

Refactors, tooling, dependency bumps, and documentation earn one closing
section and a visibly lighter treatment: a grouped list rather than cards,
prose rather than headings.

Say what it buys in terms the reader values. *The design system moved into its
own package, and an automated check fails the build if a documented style stops
working* lands because it ends in a consequence. *Extracted packages/ui* does
not.

## Words to cut

- **Ceremony**: *simply*, *just*, *easy*, *seamless*, *robust*, *powerful*.
  Calling a fix easy tells a reader who was affected that they were the problem.
- **Hedges** that dodge the fact: *some issues were addressed*, *various
  improvements*. Name them or drop them.
- **Jargon with no referent**: *refactored*, *migrated*, *idempotent*,
  *upstream*. Fine in the tracker; a wall on this page.
- **Time anchors that will not age**: *recently*, *now*, *the new*. A brief is
  read weeks later.
