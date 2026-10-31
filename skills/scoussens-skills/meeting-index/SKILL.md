---
name: meeting-index
description: >-
  Indexes recorded meetings across a period into shared themes, a searchable
  ledger, decisions, owners, and risks. Reads Plaud or another recordings-and-notes
  source. Use only when explicitly asked to index meetings, recap recordings,
  or digest calls across a period or topic. Not for a single-meeting summary,
  one factual lookup, live note-taking, or minutes.
---

# Meeting index

Turn a stretch of recorded meetings into something a person can use: not a list
of meetings with summaries stapled to them, but an index organised around the
few storylines that genuinely carried across the period, with per-meeting detail
underneath for when someone needs to go back to the source.

The value lives in the aggregate, not the parts. Any single meeting's summary
already exists wherever it was recorded — the user can read that. What they
cannot see from inside one recording is that a decision took five meetings
across four days to settle, that the same defect appeared on Monday and again on
Friday, or that the item three other workstreams are waiting on has no owner.
Surfacing that is the job. If the output reads like thirty summaries in a row it
has failed, even when every summary is accurate.

## Ask before running

This spends real time and tokens — roughly one lookup per recording plus a long
synthesis — so settle scope before starting rather than guessing and running it
twice. One question round covers unresolved consequential choices. Reuse known
settings from the user, authorized caller, or saved setup without another intake.

- **Topic** — what threads the recordings together. Offer what they said, plus
  candidates from context: a product, a client, a project, a person. "Everything
  in the window" is a legitimate answer for a general catch-up.
- **Period** — offer the last working week as the default, plus a few days and a
  month, and let an explicit range cover the rest. Do not bake a period into the
  skill; the right window depends entirely on why they are asking.
- **Output** — a setting, and `explain-to` owns settings. Load `explain-to`
  and run its step 1, the settings sheet (`references/settings-sheet.md`
  there), in this same message, passing: the artifact, an index of one
  period's recordings with threads first and a per-meeting ledger underneath;
  the setting this skill fixes, interaction, which follows the form as
  [Build the output](#build-the-output) says; the open setting, output, a
  published page (searchable, shareable, good for something they will return
  to) or a Markdown file (greppable, pasteable into a tracker or an email);
  and the rule for the Why cell, that an email or a tracker comment as the
  destination shapes the length rather than taking the full apparatus.
- **Depth**, only when the window looks large — past roughly forty recordings,
  offer "every meeting" against "the substantive ones, skipping standups and
  short syncs". Marginal recordings dilute the threads and cost real time.

## Pick a source and normalise its records

Read the adapter for whatever the user records with:

- **Plaud** — [`references/sources/plaud.md`](references/sources/plaud.md).
  Verified against a real account.
- **Anything else** — Granola, Otter, Fireflies, Fathom, a meeting-notes
  database, a directory of exported transcripts. There is no adapter shipped,
  so write against the contract in
  [`references/adding-a-source.md`](references/adding-a-source.md), which
  defines the four fields the rest of this skill needs and the two capabilities
  a source has to provide.

Every adapter normalises to the same record, and the steps below are written
against it:

```json
{ "id": "…", "title": "…", "start": "2026-01-15T15:00:00Z", "duration_ms": 3600000 }
```

## Enumerate the window; do not trust a title search

The instinct is to search recording titles for the topic. Resist it. Recording
titles — especially auto-generated ones — name the *subject of the discussion*,
not the thing the discussion was about. A search for a product's own name can
match a handful of recordings across a library of hundreds while the window
holds dozens of meetings about that product, because those meetings are titled
after what was discussed: "Example Topic A Review", "Example Topic B Cutover".
A title filter on that data does not narrow the set, it silently loses most of
it.

So **enumerate the whole window by date, then classify by content.** Running a
title search *as well* is worth it as a cross-check — if it surfaces something
the date listing missed, the listing is incomplete — but the date listing is the
population.

### Truncation will bite you, and one form is silent

Every paginated listing has a ceiling, and the two ways of hitting it announce
themselves very differently:

- **A filtered listing** usually tells you — a `truncated` flag, a `scanned`
  count, a `next` cursor. Heed it: narrow the range and list again in chunks.
- **An unfiltered paged listing often tells you nothing.** Ask for a page of 40
  and get exactly 40 back, and a complete response is indistinguishable from a
  clipped one.

For example, an unfiltered `page_size: 40` call can return exactly 40 records
that stop part-way through the earliest day of the window. An index built from
it ships without those meetings, and if one of them is where a thread began, the
index attributes that thread to a later meeting. Nothing in the response
indicates a problem.

Two habits prevent it:

- **Never open with an unfiltered paged listing.** Lead with the date range, so
  the failure mode is one that announces itself.
- **Treat "returned exactly the page size" as truncated until proven
  otherwise**, and check the boundary days specifically. Listing the first and
  last day of the window on their own is two cheap calls, and it is where
  clipping always shows up — the middle of a range is never the part that gets
  cut.

## Classify, and name what you drop

Sort each record in or out. Judge from title, duration and participants — and
when a short recording is ambiguous, fetch its notes and decide from content
rather than guessing from a title that tells you nothing.

Typical exclusions: accidental recordings (anything under about a minute, or
named with a bare timestamp), personal recordings unrelated to the topic, and a
different project or client that happens to sit in the same date range.
Interviews and one-to-ones are a judgement call — lean toward including and
labelling them rather than dropping them silently.

**Name the exclusions in the output.** "40 of 48 recordings, and here are the 8
I left out and why" is a claim the user can check. Silently indexing 40 of 48
looks identical to missing 8, and the reader has no way to tell which happened.
This is the cheapest trust you will ever buy.

## Read summaries, not full transcripts

Most sources generate a per-meeting summary — an overview, topic breakdown,
decisions, action items with owners. That is most of the raw material an index
needs, already extracted. Reach for a full transcript only when you need a
specific quote or a summary is visibly thin; transcripts are one to two orders
of magnitude larger, so a single long meeting can cost more than every summary
in the week combined.

**Batch the fetches** — six to eight at a time. They are independent, and
serialising them wastes minutes for nothing.

Three hazards worth expecting:

- **A missing summary is not a missing meeting.** Transient errors and expired
  auth are common, and auth expiry can hit a whole batch at once. Retry; if it
  still will not come back, index the record from its title and duration and say
  the summary was unavailable. Do not let the population shrink silently.
- **Very short recordings may have no summary at all**, because none was ever
  generated. That is a signal it was accidental, not a reason to retry.
- **Proper nouns and numbers are the least reliable content in any summary.**
  Speech-to-text mangles names of people, products and companies, and summaries
  inherit every variant: one product name can arrive several different ways in a
  single week, a person's name can appear in several spellings with none of them
  right, and a numeric constant can lose a digit. Normalise
  variants of the same entity to one spelling, prefer a spelling the user has
  used over one the transcript produced, and treat any name or magic number you
  have *only* from a transcript as provisional. Where such a value matters, say
  where it came from so the reader can correct it. They will know; you cannot.

## Roll up the numbers with the script

Per-meeting local times, durations, per-day totals and the overall sum are
arithmetic, and arithmetic done by hand across forty rows goes wrong in ways
that are hard to spot. Resolve `MEETING_INDEX_SKILL_DIR` to the absolute directory
containing this loaded `SKILL.md`, using the skill loader's path. Keep the working
directory in the user's project. Save the normalised records to a JSON file there
and invoke the installed script by its quoted absolute path:

```bash
python3 "$MEETING_INDEX_SKILL_DIR/scripts/rollup.py" records.json --offset-hours -5 --min-seconds 60
```

It prints per-meeting local start and duration, per-day and overall rollups, and
lists anything under the duration floor separately so accidental clips surface
instead of hiding. `--json` emits the same data for programmatic use; `--help`
has the rest.

**Input times:** the script converts timestamps with `Z` or numeric offsets to
UTC before applying the display offset. It treats timestamps without an offset
as UTC, independently of the machine's timezone. If a source uses naive local
timestamps, its adapter must resolve their timezone and any daylight-saving
ambiguity before passing them to the script.

**Deriving `--offset-hours`:** use local datetime minus UTC datetime for the same
instant, in hours. For example, 10:00 local minus 15:00 UTC is `-5`; 20:30 local
minus 15:00 UTC is `5.5`. Include both dates when the times cross midnight.
Confirm the user's offset for the meeting date rather than assuming a zone or
trusting one potentially incorrect summary header.

**Fixed-offset limit:** one invocation applies the same offset to every record;
it does not accept named timezones or adjust for daylight saving. If the window
crosses an offset change, enumerate the whole window first, partition the records
at the transition instant, and run each partition with its verified offset.
Combine the counts and durations, including same-day subtotals, without dropping
or duplicating source IDs. Preserve chronological order using the original
instants and label each partition's offset so repeated local times remain
distinct. If the offsets or transition are unknown, use `--offset-hours 0`, label
the output UTC, and disclose that local times could not be established.

## Find the threads

This is the step that decides whether the output is worth reading. Do it
deliberately, before writing anything, and read
[`references/finding-threads.md`](references/finding-threads.md) — it covers the
five patterns worth hunting for, how to tell a thread from a topic, and how to
assign each one an honest state.

## Build the output

Four layers, in this order, taking the reader from what matters down to the
source:

1. **Threads** — the storylines, each with its state and the dates to replay.
   This is the deliverable; everything below is apparatus.
2. **Ledger** — every in-scope recording in order, grouped by day: local time,
   title, participants, duration, a few substantive bullets, and its source id
   so the reader can go back. Collapsed by default — a wall of forty open
   entries buries the threads above it.
3. **Decisions** — what actually closed, separated from what was merely
   discussed, and marked *directional* where the call was a lean rather than a
   commitment. That distinction is the whole value of the section; collapsing it
   makes the period look more settled than it was.
4. **Owners and risks** — open items by person, then what is accruing cost.
   Include an explicit unassigned row when load-bearing work has no owner. If
   deadlines were mostly absent from the meetings, say so — that absence is
   itself a finding.

For a **published page**, treat it as a tool rather than a document: it is
scanned and operated, not read top to bottom. That means live search across
every entry, filters for tracks or categories, collapsed ledger rows, and
category colour that encodes real classification rather than decoration. For
**Markdown**, keep the same four layers and lead with the threads; drop the
interaction, keep the structure. If the sheet settled on an email or a tracker
comment as the destination, let that shape the length rather than forcing the
full apparatus into it.

Publish a page only with authority for its content and audience at the agreed
destination, using saved facts or narrow capability inspection as
`explain-to`'s `references/formats.md` ("Hand-offs by harness")
describes.

## Report what only the aggregate shows

When handing off, do not recite the sections; the user can see those. Lead with
the two or three findings that were invisible from inside any single meeting: the
recurrence, the unowned dependency, the independent convergence, the decision
that took four days.

If the lookup itself taught you something about the data — a filter that
under-recalled, a date that disagreed with its own summary, a recording that
turned out to be something else entirely — say that too. It tells the user how
much to trust the population, which is the one thing they cannot verify from the
output alone.
