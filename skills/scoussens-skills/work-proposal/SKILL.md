---
name: work-proposal
description: Turn a body of scoped work into a client-ready proposal — effort and cost grounded in the actual codebase rather than ticket titles, priced against whatever commercial agreement already exists, with anything not yet knowable named rather than averaged into a range, and delivered as a themed Artifact page, a PDF, or email-ready Markdown. Use when the user asks to scope and price work — "write a proposal", "what would it take to build X", "quote this work", "put together an SOW", "estimate this epic for the client", "how much for phase 2". Do not load it to estimate one ticket, to plan a sprint for an internal team, or to answer how long a single change takes; answer those directly instead.
---

# Work proposal

A proposal is a number someone will hold you to. Everything else on the page —
the sequencing, the exclusions, the prose — exists to make that number
defensible. So the work is mostly research, and the writing is the short part.

Two failures account for most bad proposals, and both happen before a word is
written. The first is estimating from ticket titles, which produces confident
numbers for work nobody has looked at. The second is inventing commercial terms
that already exist somewhere, which either undercuts an agreement the client
signed or contradicts it. Close both before drafting.

Build it in this order: find the commercial ground, read the code, then write.

## Ask four questions first

Three of these you cannot derive, and the fourth changes the whole page.

1. **Which work, and is anything already agreed?** Get the specific list — a
   tracker project, an email, a set of issue IDs. Ask whether the client has
   already seen a scope list, because a proposal that renames or re-groups what
   they agreed reads as a different proposal.
2. **What does the delivery team actually cost and how fast does it work?**
   Both are house facts you cannot infer. See
   [Find the commercial ground first](#find-the-commercial-ground-first).
3. **Artifact, PDF, or email?** Each carries different constraints, and the
   choice changes how you write, not just how you export. See
   [references/output-formats.md](references/output-formats.md).
4. **Who reads it, and what decision are they making?** A founder funding it
   personally, a board voting on it, and a procurement team comparing bids need
   the same facts ordered differently. A nonprofit board wants to know what it
   can decline; a procurement team wants line items it can compare.

## Find the commercial ground first

**Do not invent a rate.** Most ongoing relationships already have one, written
down somewhere, and a proposal that quotes a different number is worse than
one that quotes nothing. Look before asking:

```bash
rg -il 'retainer|per hour|/hr|hourly|rate card|statement of work|\bSOW\b|pricing' \
   docs/ contracts/ business/ *.md 2>/dev/null
```

Also check published documents the repository does not hold — prior proposals,
pricing pages, or agreements the user shared earlier in the conversation. If
the client is on a support plan, its additional-hours rate is almost always
the right rate to quote, and the plan may carry entitlements that reduce the
bill — included hours that can be redirected, free scoping, a partner discount.
Apply them; they are the client's already, and finding them is worth more
goodwill than any discount you invent.

When there is genuinely nothing, ask. Do not guess a market rate.

The team's delivery pace is the other half and is equally unguessable.
Published industry hours assume a delivery model that may not be yours — a team
building with AI assistance can run at a substantial multiple of them, and a
proposal that ignores this overcharges by that multiple. Ask what a comparable
past item actually took, and calibrate to that.
[references/estimating.md](references/estimating.md) covers turning that into
per-item numbers.

## Ground every estimate in the code

This is where a proposal earns its accuracy, and it is the step most often
skipped. **Read the code for each item before you size it.** Ticket titles
describe intentions; the codebase decides cost, and the two disagree
constantly. In both directions:

- A "small" wording change can touch a content model, an editor, a web
  renderer, and a PDF pipeline, because the field it needs does not exist.
- A "build an integration" item can turn out half-built, with the schema,
  the service method, and the validation already in place and only a router
  missing.

Neither is visible from the tracker. Both change the number by multiples.

For each item, find the models, services, and screens it touches, and answer
three questions: what exists, what is missing, and what else breaks if it
changes. Then write down what you found — a proposal that says *the PDF builder
is already in good shape* has told the reader why one line is cheap, and a
reader who understands one number trusts the rest.

Where a field or table already exists but nothing reads it, say so. Dead
scaffolding is common, and it is the difference between extending a mechanism
and building one.

## Price what you can, name what you cannot

Some items cannot be estimated until someone makes a decision. Averaging over
that produces a number that is wrong in a way nobody can see.

Give those their own section, state exactly what is blocking them and who owns
it, and offer an indicative range marked as indicative. A client would far
rather see *two items need half an hour of your time before we can cost them*
than a total that quietly absorbs the uncertainty.

The same applies to third-party costs. Carrier fees, per-seat licences, and API
pricing move, and quoting them from memory is how a proposal acquires a number
that was true a year ago. Give the shape, mark it as needing a live quote, and
say you will confirm it.

## Look for the cost that dominates, even when it is not yours

The largest number in a proposal is often not the engineering. Content
production, data cleanup, migration, review, and training all attach to
software work and routinely exceed it.

Measure it rather than gesturing at it. Counting the words in a corpus, the
rows in a table, or the screens in a flow takes minutes and can reframe an
entire item — the software may be a fortnight while the content behind it is a
year of somebody's life. A client who learns that from your proposal will trust
the rest of it; a client who learns it three months in will not.

Naming a cost that falls outside your invoice is not scope-creep and not
someone else's problem. It is the difference between a proposal and a quote.

## Sequence by dependency, not by priority

Order the work by what makes the rest cheaper. Where one item is the surface
several others get built into, doing it first is the difference between
building those once and building them twice — and that reasoning belongs on the
page, because it is the client's money either way.

Use a numbered or phased structure only where the order is real. Where items
are genuinely independent, say so, because that is what tells a client they can
fund one thing this quarter and defer the rest.

Flag any item with an external deadline nobody controls — a season, a renewal,
a regulatory date. It is the one thing on the page that cannot slip, and it is
usually not the highest-priority item.

## Take the theme from the project

A proposal that looks like the thing it describes reads as the client's
document rather than a vendor's template. When the project ships a design
system, use it — read the tokens, take the literal values, honour the
constraints the file documents. When it does not, derive a restrained palette
from the client's public brand and say in your reply that you chose it rather
than found it.

Theme is not decoration here. It is the cheapest available signal that you
have read their work.
[references/output-formats.md](references/output-formats.md) covers finding a
design system, deriving a palette when there is none, and the constraints each
delivery format puts on it.

## Show what you found along the way

Reading a codebase closely surfaces things nobody asked about — a bug, a
silent failure, a piece of data captured but never used. Give the real ones a
short section of their own, stated plainly and without alarm, and say clearly
that they are outside the proposed scope.

This is the section clients remember. It demonstrates that the estimates came
from looking rather than guessing, and it is the honest moment to raise
anything that would be awkward to mention later.

Keep it to things you actually found and can point at. Three real findings
beat a list of generic recommendations.

## Check the arithmetic before you send

A proposal with a column that does not sum destroys the credibility of every
other number on the page, and it is the easiest error to make while editing
ranges by hand.

```bash
python3 scripts/check-totals.py <file> --rate <hourly-rate>
```

The script reads HTML or Markdown tables, sums each numeric and currency
column including ranges like `16–20` and `$1,920–$2,400`, compares them to any
stated total, and — given a rate — checks that money equals hours times that
rate on every row. Run it after every edit pass, not once at the end.

## Deliver it

Ask which format; do not assume. Each one changes the writing.

| | Best for | Constraint that shapes the writing |
| --- | --- | --- |
| **Artifact** | A client who will forward a link; anything with tables | Private until shared. Renders in the reader's theme, so both must work |
| **PDF** | Attachments, board packs, signatures, print | Fixed width, no dark theme, page breaks are yours to control |
| **Email / Markdown** | A short proposal inside a thread | Clients strip CSS. No theme survives. Keep tables small or drop them |

Mechanics for each, including rendering a PDF with headless Chrome via
`scripts/html-to-pdf.sh`, are in
[references/output-formats.md](references/output-formats.md).

Write the prose plainly whatever the format. If the `speak-clearly` skill is
available, apply it — a proposal is exactly the document where filler and
future tense do damage, because both read as hedging about a number.

Close your reply by stating what you verified, naming the judgement calls the
user should check before sending, and listing anything you deliberately left
out.

## Do not use this skill for

- **Estimating one ticket.** Read it, look at the code, answer.
- **Internal sprint planning.** A proposal is for someone deciding whether to
  fund work. A plan is for a team already committed to it.
- **A pitch or capability deck.** Those sell a relationship. This prices a
  defined body of work for a client you already have.

## Done when

- Every rate, discount, and entitlement traces to an existing agreement, or the
  user supplied it deliberately.
- Hours reflect the delivery team's real pace, not a generic industry figure.
- Every priced item was sized after reading the code it touches, and the page
  says what made the expensive ones expensive.
- Items that cannot yet be priced sit in their own section, naming what blocks
  them and who owns the decision.
- Third-party and recurring costs are marked as needing a live quote rather
  than stated from memory.
- Any cost that falls outside your invoice but dominates the project is named
  and, where possible, measured.
- Sequencing encodes real dependencies, external deadlines are flagged, and
  independent items are identified as such.
- Every column sums, and money matches hours times the rate.
- The theme came from the project, or your reply says you chose it.
- Your reply names the judgement calls the user should check.
