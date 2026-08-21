---
name: release-brief
description: Turn a window of shipped work into a brief for a non-technical stakeholder — verified against what actually reached production, grouped by consequence, referenced back to issue-tracker IDs and pull request numbers, and delivered as a themed Artifact page or Markdown. Load this only when the user explicitly asks for such a brief — "write a release brief", "board update", "brief the client on this sprint", "stakeholder summary of what we shipped". Do not load it to answer what changed recently, to generate a changelog or technical release notes, to summarise a single pull request, or to write a commit message; answer those directly instead.
---

# Release brief

A release brief tells someone who does not read code what changed and why it
mattered. Its only asset is trust: a stakeholder cannot check your claims, so
one overstatement — a ticket called closed when it is still open, a fix called
live when it sits on a branch — costs more than a whole page of polish buys.

Build it in this order: establish ground truth, agree the story, then write.

## Ask three questions first

Two of these you cannot derive from the repository, and the third changes what
you build. Ask them before gathering anything.

1. **Which window, and is the unit a period or a release?** These are two
   different documents and the distinction decides what goes in. See
   [Period or release](#period-or-release) below; ask before gathering, because
   the two modes select different sets of work.
2. **Who reads it, and what should they conclude?** A board, a customer
   contact, an exec team, and an investor care about different things, and the
   same set of changes usually supports several honest stories. Offer two or
   three framings you can actually defend from the work, and let the user pick.
   This is a business judgement, not an engineering one.
3. **Artifact page, Markdown, or both?** A published Artifact carries the
   customer's own visual identity and a link they can forward. Markdown pastes
   into an email, a doc, or a tracker comment. Ask; do not assume.

## Period or release

A brief covers either a stretch of calendar time or one or more named
releases. Both are legitimate; they answer different questions and they select
different work.

**Period-anchored** — "what did we ship this week", "this sprint". The reader
wants a sense of the period. Releases inside it are incidental: count them, but
do not organise the page around them.

**Release-anchored** — "brief the client on v2.3", "what went out on Thursday".
The reader is asking about a named thing. Show the boundaries, and say which
release each item belongs to when there is more than one.

The practical difference is the selection rule, and getting it wrong is the
easiest way to publish a brief that is quietly incomplete:

| | Period-anchored | Release-anchored |
| --- | --- | --- |
| Include | Work that **reached production** inside the window | The **contents of the named releases**, whenever the work was merged |
| Boundaries | Counted, not shown | Shown, and used as structure when there are several |
| Ages | Yes — stamp it | No — a shipped release is immutable |

**Merged-in-window and released-in-window are different sets.** In a two-stage
repository a change merges to the integration branch on one day and is promoted
days later, so a period brief that filters on merge date drops work that went
live inside the window and includes work that has not gone live at all. Filter
on the promotion that carried it, not on when its pull request merged.

### Finding the release boundaries

On the production branch, `--first-parent` gives the promotion sequence — one
entry per release, in order:

```bash
git log --first-parent --date=short --pretty='%h %ad %s' origin/<production-branch>
```

Each entry is a release. To read one release's contents, take the range between
two consecutive entries; to read a tagged release, use `git log <prev-tag>..<tag>`.

Trunk-based repositories have no git-visible boundary, because there the
release *is* the deploy. Get the sequence from the deploy platform's own
records instead, and say in the brief that a release means a deploy.

### Do not count promotions as changes

A promotion — the merge or squash that carries the integration branch into
production — is not itself a change. Counting the four promotions alongside the
31 changes they delivered inflates the headline and double-counts the work.
Report them separately: *31 changes merged, carried live by 4 releases.*

### Period briefs need an as-of stamp

A period brief is a snapshot: work merged an hour after publication makes its
"nothing is queued" claim false without anything being edited. Put the time it
reflects next to the date range, and say in the footer that later work is not
represented. A release brief needs no such stamp.

## Establish what actually shipped

Do this before writing a single sentence, because everything downstream
inherits its accuracy.

**A commit-range comparison lies after a squash merge.** `git log base..head`
lists commits by ancestry, and squashing rewrites content into a new commit
whose parents differ — so work that is fully released still shows as
"unmerged". Compare trees instead:

```bash
git fetch origin <production-branch> <integration-branch>
git diff --stat origin/<production-branch> origin/<integration-branch>
```

Empty output means the two branches hold identical content and nothing is
waiting. Non-empty output is the real backlog, and the brief must say which
items are live and which are queued.

Then collect the work and probe production. For a period brief, select what
reached production inside the window; for a release brief, select each named
release's contents. This lists candidates by merge date, which is a starting
point rather than the answer:

```bash
gh pr list --state merged --limit 100 \
  --json number,title,mergedAt,baseRefName \
  --jq '.[] | select(.mergedAt >= "<start>") | "\(.number)|\(.mergedAt[0:10])|\(.baseRefName)|\(.title)"'
```

`scripts/shipped-in-window.sh` runs this sequence and prints the ship-state
verdict, the release boundaries, the merged pull requests split into product
work and promotions, and every tracker ID it can find. Pass `--release <ref>` to
read one release's contents instead of a date window. For the
failure modes it guards against — release branches, cherry-picks, reverts,
deploys that lag the merge — read
[references/verifying-ship-state.md](references/verifying-ship-state.md).

## Join the code to the tracker

Work with whatever tracker the customer uses. The brief needs five facts per
item, and where they come from matters less than that they are real:

| Fact | Why the brief needs it |
| --- | --- |
| Identifier and URL | Lets a reader follow the trail themselves |
| Title | The tracker's words, not your paraphrase of a commit |
| Priority or severity | The honest basis for ordering and for any visual weight |
| Type — bug, feature, task | Distinguishes "we broke it and fixed it" from "we built it" |
| Status | Separates *shipped* from *closed*; they diverge more than you expect |

Tracker IDs usually appear in commit subjects, pull request titles, branch
names, or a `Fixes …` line in a pull request body. Harvest them from all four,
then read each issue through the tracker's own MCP server, CLI, or API.

**Never infer a field the tracker does not record.** If an issue carries no
type label, print the priority alone. If its status is *In Review* rather than
*Done*, say the fix shipped and the issue stays open pending confirmation.
Inferring feels harmless one item at a time and is how a trustworthy document
acquires three small lies. When a tracker is unreachable, build the brief from
commit and pull request titles and tell the user which facts are missing.

## Group by consequence

Chronology is how the work happened; consequence is how the reader
experiences it. Sort into four to seven themed sections, most consequential
first, and lead each with a sentence naming the surface it touches — the
roster import, the invitation flow, the reporting page.

Foundation work — refactors, tooling, dependency and documentation changes —
belongs in one closing section under a visibly lighter treatment. It is real
work and it earns a mention, but no stakeholder decision rides on it, and
giving it card-for-card parity with a data-loss fix misrepresents the week.

Reach for a structural device only where it encodes something true. A severity
stripe keyed to recorded priority is information. Numbered markers on themed
sections are decoration, because a ranked list is not a sequence.

## Write from the reader's side of the screen

Each item leads with what a person would notice, in their vocabulary. Detail
follows in a sentence or two, then the tracker and pull request references sit
quietly underneath.

> **Re-importing the roster no longer erases what staff wrote**
> Running the import a second time was blanking staff-authored notes on people
> who have no login of their own. Four fixes closed all four paths.
> `PM-824 · PR #682`

Not: *fixed upsert to scope field writes on the account-less path.* That
sentence is true and tells the reader nothing.

For the sentence patterns that carry this voice, the way to describe a security
fix without alarming or minimising, and how to phrase counts you can defend,
read [references/writing-the-items.md](references/writing-the-items.md).

## Theme it from the customer's own repository

A brief that looks like the product it describes reads as the customer's
document rather than a vendor's template. When the repository ships a design
system, use it: read the tokens file, take the literal brand values, and honour
the constraints it documents — an accessible text variant of an accent colour
exists because someone measured the contrast.

Reproduce the palette and typefaces exactly rather than approximating them, and
respect any rule the stylesheet states about where a colour may be used.
[references/theming-from-a-repo.md](references/theming-from-a-repo.md) covers
finding the design system, substituting licensed typefaces with hosted
equivalents, and deriving a dark palette when the product ships only a light
one.

With no design system to draw on, choose a restrained palette from the
customer's public brand and say in your reply that you did.

## Deliver it

For an Artifact, load the `artifact-design` skill before writing the page, give
the page a specific name, and hand the user the URL along with a note that it
stays private until they share it.

For Markdown, use heading levels for the section hierarchy and keep the
reference line on its own line beneath each item so it survives pasting into
email.

Either way, close your reply by stating what you verified, listing any judgement
call the user should check, and naming anything you left out.

## Do not use this skill for

- **Answering what changed recently.** Read the log and answer.
- **Changelogs and technical release notes.** Those address engineers and are
  organised by component and version, not by consequence.
- **Summarising one pull request**, or writing a commit message.

It is invoked deliberately, by name or by an explicit request for a brief.
Producing one unasked wastes a large amount of work on a document nobody
requested.

## Done when

- The window is stated on the page and matches what the user asked for, and a
  period brief carries the time it reflects.
- Work was selected by the rule its mode requires — reached-production for a
  period, release contents for a release — not by merge date alone.
- Promotions are reported separately from the changes they carried.
- Every claim that something is live was checked against production, and
  anything still queued is labelled as such.
- Every identifier, title, priority, type, and status came from the tracker; no
  field was inferred to fill a gap.
- Counts are phrased so they stay true — *shipped* rather than *closed* when
  an issue remains open — and any exception is named rather than rounded away.
- Sections run most consequential first, with foundation work last and lighter.
- Each item opens with an observable effect and carries its tracker and pull
  request references.
- Your reply names the judgement calls the user should check.
