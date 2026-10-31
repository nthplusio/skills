---
name: release-brief
description: >-
  Writes non-technical release briefs from verified production evidence,
  grouped by consequence and linked to tickets and PRs, as HTML or Markdown.
  Use only for explicit release-brief, board-update, or client/stakeholder
  shipped-work requests. Not for general recent-change recaps, changelogs,
  technical release notes, single-PR summaries, or commit messages.
---

# Release brief

A release brief tells someone who does not read code what changed and why it
mattered. Its only asset is trust: a stakeholder cannot check your claims, so
one overstatement — a ticket called closed when it is still open, a fix called
live when it sits on a branch — costs more than a whole page of polish buys.

Build it in this order: establish ground truth, agree the story, then write.

## Ask two questions and show the sheet first

Reuse known settings from the user, authorized caller, or saved setup. Ask
only unresolved consequential choices below in one message before gathering,
each with a bold recommendation. Repository evidence alone cannot choose the
user's window or business framing.

1. **Which window, and is the unit a period or a release?** These are two
   different documents and the distinction decides what goes in. See
   [Period or release](#period-or-release) below; ask before gathering, because
   the two modes select different sets of work.
2. **What should the reader conclude?** A board, a customer contact, an exec
   team, and an investor care about different things, and the same set of
   changes usually supports several honest stories. Offer two or three framings
   you can actually defend from the work, and let the user pick. This is a
   business judgement, not an engineering one.
3. **Which form.** The form is a setting, and `explain-to` owns settings. Load
   `explain-to` and run its step 1, the settings sheet
   (`references/settings-sheet.md` there), passing these facts:
   - **The artifact.** A release brief: one window of shipped work, verified
     against production and grouped by consequence.
   - **Fixed settings.** Reader: the *business stakeholder* profile, because
     the brief exists for someone who does not read code (see
     [Write from the reader's side of the screen](#write-from-the-readers-side-of-the-screen)).
     Interaction, length, and anchor follow that profile; the budget applies
     per item, so the whole brief runs longer than one explanation.
   - **The open setting.** Output. An HTML page carries the customer's own
     visual identity and a link they can forward; Markdown survives pasting
     into an email, a doc, or a tracker comment. Both at once is a legitimate
     answer.

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

On a branch that receives only release promotions, `--first-parent` gives the
promotion sequence. Otherwise it lists candidate boundaries, not releases:

```bash
git log --first-parent --date=short --pretty='%h %ad %s' origin/<production-branch>
```

Resolve the previous and current release from tags or deployment records and
record both commit IDs. Use `<previous>..<current>`: the previous boundary is
excluded and the current boundary is included. Adjacent first-parent entries
work only when the release process confirms that each entry is a promotion.
A tag can span many commits; its parent is not necessarily the previous release.
If either boundary is missing, ambiguous, or on an unrelated history, label the
contents unknown and resolve the gap before claiming a complete release list.

Trunk-based repositories have no git-visible boundary, because there the
release *is* the deploy. Get the sequence from the deploy platform's own
records instead, and say in the brief that a release means a deploy.

### Do not count promotions as changes

A promotion — the merge or squash that carries the integration branch into
production — is not itself a change. Counting, say, four promotions alongside
the 30 changes they delivered inflates the headline and double-counts the work.
Report them separately: *30 changes merged, carried live by 4 releases.*

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

Only a successful fetch and comparison can establish identical branch content.
A failed fetch, missing ref, or failed comparison leaves the state **unknown**;
empty output from a failed command is not equality. A successful empty diff
proves equal trees, not deployment or an empty deployment queue. Read a non-empty
diff to distinguish product changes from production-only fixes or release files.

Then collect the work and probe production. For a period brief, select what
reached production inside the window; for a release brief, select each named
release's contents. This lists candidates by merge date, which is a starting
point rather than the answer. Filter on the server, once per branch: `--limit`
pages by creation date, so filtering the output yourself drops a long-lived
pull request that merged inside the window.

```bash
gh pr list --state merged --base <branch> --search "merged:>=<start>" --limit 300 \
  --json number,title,mergedAt,baseRefName \
  --jq '.[] | "\(.number)|\(.mergedAt[0:10])|\(.baseRefName)|\(.title)"'
```

`scripts/shipped-in-window.sh` runs this sequence and prints the ship-state
comparison, candidate release boundaries, merged pull requests split into product
work and promotions, and every tracker ID it can find. It does not verify
deployment. In a single-branch repository there are no separate promotions to
subtract; deployment records still determine which merges shipped. Pass
`--release <current-ref> --previous <previous-ref>` to read explicit release
contents instead of a date window. The helper exits nonzero on Git evidence
failures and labels unavailable forge data unknown; report those gaps rather
than treating them as empty results. For the
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
first, and lead each with a sentence naming the surface it touches — the import
screen, the checkout flow, the reporting page.

Foundation work — refactors, tooling, dependency and documentation changes —
belongs in one closing section under a visibly lighter treatment. It is real
work and it earns a mention, but no stakeholder decision rides on it, and
giving it card-for-card parity with a data-loss fix misrepresents the week.

Reach for a structural device only where it encodes something true. A severity
stripe keyed to recorded priority is information. Numbered markers on themed
sections are decoration, because a ranked list is not a sequence.

## Write from the reader's side of the screen

The reader is the **business stakeholder** profile in the `explain-to` skill's
`references/audiences.md`, when that skill is installed beside this one. Its
vocabulary list applies throughout, and its reading budget applies to each
item, not to the brief as a whole.

Each item leads with what a person would notice, in their vocabulary. Detail
follows in a sentence or two, then the tracker and pull request references sit
quietly underneath.

> **Re-importing the customer list no longer erases notes staff typed**
> Running the import a second time was blanking notes on records with no linked
> account. Four fixes closed all four paths.
> `ABC-412 · PR #1189`

Not: *fixed upsert to scope field writes on the unlinked path.* That sentence
is true and tells the reader nothing.

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

Build the agreed form. For an HTML page, use saved destination facts or narrow
capability inspection as `explain-to`'s `references/formats.md` ("Hand-offs by
harness") describes. If an `artifact-design` skill is available, load it before
writing the page. Before uploading, verify the destination's access controls and
state who can see it: named users, a workspace, anyone with the link, or the
public. An unlisted URL is not private. Publish only when the user has authorized
that audience; otherwise keep the draft in-thread or local and request approval.
If access cannot be verified, label it **unknown** and hold publication. After
authorized publication, give the page a specific name and report the URL with
the verified audience, not a blanket privacy promise.

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
  anything still queued is labelled as such. Failed or cancelled deployments
  remain unverified; branch equality never overrides deployment evidence.
- Every identifier, title, priority, type, and status came from the tracker; no
  field was inferred to fill a gap.
- Counts are phrased so they stay true — *shipped* rather than *closed* when
  an issue remains open — and any exception is named rather than rounded away.
- Sections run most consequential first, with foundation work last and lighter.
- Each item opens with an observable effect and carries its tracker and pull
  request references.
- Your reply names the judgement calls the user should check.
- The delivery audience was verified and authorized, or publication is held
  with the missing access evidence named.
