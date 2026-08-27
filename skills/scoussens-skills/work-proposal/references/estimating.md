# Estimating from the code

How to turn a scope list into hours you can defend when someone asks where a
number came from.

## Contents

- [Calibrate to the team, not to the industry](#calibrate-to-the-team-not-to-the-industry)
- [Read before you size](#read-before-you-size)
- [What the code tells you that the ticket does not](#what-the-code-tells-you-that-the-ticket-does-not)
- [Ranges, and what the two ends mean](#ranges-and-what-the-two-ends-mean)
- [Points and hours are different currencies](#points-and-hours-are-different-currencies)
- [Items you cannot price yet](#items-you-cannot-price-yet)
- [Measuring the cost that is not yours](#measuring-the-cost-that-is-not-yours)

## Calibrate to the team, not to the industry

Estimating guides encode a delivery model. If the team's differs — AI-assisted
implementation is the common case, and it can run at a large multiple of
hand-written pace — every number inherited from those guides is wrong by that
multiple, in the client's disfavour.

You cannot detect the multiplier from the repository. Ask for an anchor: one
recent item, what it involved, and what it actually took. Size everything
relative to that, and if the user later corrects the scale, rescale
proportionally rather than re-deriving.

Whatever the multiplier, say on the page why the hours look the way they do.
A reader who sees nine hours for work described as touching four layers will
assume you misunderstood the scope unless a sentence explains it. State the
delivery model plainly and say whether the saving is passed on or kept.

## Read before you size

For each item, open the code. The questions worth answering are always the
same three:

1. **What already exists?** Models, columns, service methods, routes, screens.
2. **What is missing?** The specific thing that has to be built.
3. **What else moves if this changes?** Callers, renderers, exports, tests,
   cached artefacts.

Question three is where estimates go wrong. A content-model change propagates
into every renderer; a new field propagates into every form that writes the
record. Count those surfaces before writing a number.

Useful opening moves:

```bash
rg -n 'model <Entity>' --type prisma          # or the ORM's schema equivalent
rg -l '<entity>\.(findMany|findUnique|create|update)' --glob '!**/*test*'
rg -c 'export (default )?function|export const' <ui-directory>
```

Counting the call sites of the thing you intend to change is the single most
predictive number available, and it takes one command. A change behind five
call sites and a change behind fifty are not the same change.

## What the code tells you that the ticket does not

Patterns worth naming on the page when you find them, because each one explains
a number that would otherwise look arbitrary:

**Dead scaffolding.** A column, enum, or flag that exists and nothing reads.
Grep for it excluding generated code. If nothing consults it, the item is
building a mechanism, not extending one — but the schema work is already done,
which usually makes it cheaper than it sounds, not dearer.

**The half-built path.** Schema, service, and validation present; one link
missing. Common where a feature was specced then deprioritised. These are the
cheapest items on any list and the most satisfying to report.

**The absent seam.** The ticket asks for something the model has nowhere to
put — prose in a structure that only holds questions, a link in a field that
only holds a string. This is the expensive shape, because it means a schema
change plus every reader of that schema. Say so explicitly; it is the main
reason a cheap-sounding item is not cheap.

**The shared surface.** Several items landing in the same file or component.
Worth pairing them in the sequencing so the surface is touched once. Name the
pairing on the page — it reads as competence and it is true.

## Ranges, and what the two ends mean

Give every item a range, and define the ends once so the reader can interpret
all of them:

> The low end assumes the open questions on each item resolve cleanly, the high
> end assumes they do not.

That is honest and it is checkable. Avoid padding a single number to feel safe:
a padded point estimate loses the information a range carries, and a client
comparing two proposals reads the padding as the price.

Keep the ratio between the ends proportional to what you actually do not know.
A well-understood item is a narrow range. An item with an unresolved
architectural fork inside it is a wide one — or belongs in the unpriced
section instead.

## Points and hours are different currencies

Where the tracker carries story points, leave them alone when hours change.
Points measure complexity; hours measure delivery. A team that gets faster does
not make its past work more complex, and rescaling points to match a new pace
destroys every historical comparison the tracker holds.

If a ticket body carries an old hour figure that now contradicts the proposal,
correct it in the ticket with a note saying why, rather than leaving the
tracker and the proposal disagreeing where a client might see both.

## Items you cannot price yet

An item belongs in its own unpriced section when a decision that is not yours
would change the number by more than the range would cover. Two common shapes:

- **The client owes an answer.** Logistics, policy, which of three behaviours
  they want. Write the specific questions down; usually there are fewer than
  five and they take one call.
- **The item is really several projects.** "Translations", "reporting",
  "mobile" often hide two or three efforts with different owners and wildly
  different costs. Split it on the page, cost the parts separately, and
  recommend a first slice.

For both, give an indicative range and mark it indicative. The point is to show
the client the shape of the commitment without pretending to a precision you
do not have.

## Measuring the cost that is not yours

When an item depends on work the client performs — content, translation,
cleanup, review — measure the volume rather than describing it. The measurement
is usually a short script and it frequently changes the recommendation.

Count the real unit: words of prose in a corpus, rows needing review, screens
to redesign. Exclude what does not need the work — structural keys, generated
records, boilerplate — because including them inflates the number and the
inflation is the first thing a sceptical reader finds.

Then present the routes honestly, including the ones that reduce your own
invoice. Where automation can do a first pass cheaply, say so and price the
human review separately, because review is usually the real constraint. A
recommendation to do a small slice first, prove it, and decide from there is
almost always the right one when the total is large.
