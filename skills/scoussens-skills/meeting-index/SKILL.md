---
name: meeting-index
description: Index a period of recorded meetings — the threads that carried across them, a searchable per-meeting ledger, and what got decided, who owns it, and what is at risk — reading from Plaud, or any source that can list recordings and return per-meeting notes. Load this only when the user explicitly asks for such an index — "index my meetings from last week", "what did we discuss about the migration", "recap my recordings this sprint", "digest my calls with that client", "what came out of this month's meetings". Do not load it to summarise a single meeting, to answer one factual question about something that was said, to take notes on a call in progress, or to write minutes — answer those directly instead, because this sweeps every recording in a window and costs a lookup per meeting.
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
twice. One question round covers it. Skip anything the user already specified in
their own words.

- **Topic** — what threads the recordings together. Offer what they said, plus
  candidates from context: a product, a client, a project, a person. "Everything
  in the window" is a legitimate answer for a general catch-up.
- **Period** — offer the last working week as the default, plus a few days and a
  month, and let an explicit range cover the rest. Do not bake a period into the
  skill; the right window depends entirely on why they are asking.
- **Output** — a published page (searchable, shareable, good for something they
  will return to) or a Markdown file (greppable, pasteable into a tracker or an
  email). Ask rather than assuming; the destination changes the shape.
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
{ "id": "…", "title": "…", "start": "2026-08-21T18:06:03Z", "duration_ms": 4769000 }
```

## Enumerate the window; do not trust a title search

The instinct is to search recording titles for the topic. Resist it. Recording
titles — especially auto-generated ones — name the *subject of the discussion*,
not the thing the discussion was about. A search for a product's own name once
matched 9 recordings across a 500-record library while the window actually held
41 meetings about it, because those meetings were titled "Auth Migration
Review", "Schema Cutover", "Billing Rework". A title filter on that data does
not narrow the set, it silently loses most of it.

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

That is not hypothetical. An unfiltered `page_size: 40` call once returned
exactly 40 records that happened to stop part-way through the earliest day of
the window. The resulting index shipped missing five meetings and nearly three
hours — including a 77-minute architecture review that was the origin of two of
the threads the index had attributed to later meetings. Nothing in the response
indicated a problem.

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

**Name the exclusions in the output.** "39 of 47 recordings, and here are the 8
I left out and why" is a claim the user can check. Silently indexing 39 of 47
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
  inherit every variant: one product name came through four different ways in a
  single week, a colleague's name appeared as five different spellings and every
  one was wrong, and a numeric constant arrived with a digit missing. Normalise
  variants of the same entity to one spelling, prefer a spelling the user has
  used over one the transcript produced, and treat any name or magic number you
  have *only* from a transcript as provisional. Where such a value matters, say
  where it came from so the reader can correct it. They will know; you cannot.

## Roll up the numbers with the script

Per-meeting local times, durations, per-day totals and the overall sum are
arithmetic, and arithmetic done by hand across forty rows goes wrong in ways
that are hard to spot. Save the normalised records to a JSON file and run:

```bash
python3 scripts/rollup.py records.json --offset-hours -5 --min-seconds 60
```

It prints per-meeting local start and duration, per-day and overall rollups, and
lists anything under the duration floor separately so accidental clips surface
instead of hiding. `--json` emits the same data for programmatic use; `--help`
has the rest.

**Deriving `--offset-hours`:** timestamps are usually UTC and the user thinks in
local time. Do not assume a zone. Take any record whose summary quotes a local
time, subtract it from that record's `start`, and pass the difference.

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
interaction, keep the structure. If the user named a destination — an email, a
tracker comment — let that shape the length rather than forcing the full
apparatus into it.

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
