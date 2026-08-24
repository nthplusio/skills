# Adding a source

Only Plaud ships with a verified adapter. Everything else — Granola, Otter,
Fireflies, Fathom, Zoom's own summaries, a meeting-notes database, a directory
of exported transcripts — needs one written against this contract. It is short,
because the skill needs very little from a source.

## What a source has to provide

**Two capabilities.** If a source has both, it works.

1. **Enumerate recordings over a date range**, returning at minimum an id, a
   title, a start timestamp and a duration.
2. **Return per-recording content by id** — ideally a generated summary, and a
   full transcript only if that is all there is.

**Four fields**, normalised to this record:

```json
{ "id": "…", "title": "…", "start": "2026-08-21T18:06:03Z", "duration_ms": 4769000 }
```

| Field | Meaning | Watch for |
| --- | --- | --- |
| `id` | Stable identifier for later calls and for reader traceability | Must survive into the output so a reader can find the source |
| `title` | Human-readable name | Usually auto-generated, usually names the *topic* rather than the subject |
| `start` | ISO 8601 start time | Note whether it is UTC or local — you need this for the offset |
| `duration_ms` | Length in **milliseconds** | Seconds and milliseconds are easy to confuse; a 1000× error is obvious in a rollup, which is one reason to run the script |

`scripts/rollup.py` reads these names, and also accepts the common aliases
`name` → `title`, `start_at`/`created_at` → `start`, and `duration` →
`duration_ms`, so many raw API responses can be passed straight through.

## What to write down

An adapter document should answer six questions. Everything else is optional.

1. **Which calls**, with the exact tool or endpoint names, and which one is the
   workhorse for summaries.
2. **The field mapping** to the four normalised fields, including units.
3. **How to enumerate a window** — and whether title or full-text search
   under-recalls, which it usually does.
4. **How truncation behaves**, and critically *whether it is visible*. A source
   that silently caps a page is the single most dangerous thing here, because a
   clipped response looks exactly like a complete one.
5. **Summary versus transcript** — which call returns which, their relative
   size, and any call that bundles a transcript you did not ask for.
6. **Timezone** — what the timestamps are in, and how to recover the user's
   local offset rather than assuming one.

Then add the source to the list in `SKILL.md` under "Pick a source", and say
plainly whether the adapter was verified against a real account or written from
documentation. That distinction matters to whoever reads it next.

## Things that are true of most sources

Worth checking rather than rediscovering:

- **Title search under-recalls.** Auto-generated titles name what was discussed,
  not what it was about. Enumerate by date and classify by content.
- **Summaries beat transcripts by one to two orders of magnitude** in size, for
  most of the same information. Fetch transcripts only for quotes.
- **Some call bundles the transcript** with the metadata, and it is rarely the
  one you want.
- **Auth expires mid-sweep**, often taking a whole batch with it. Retry rather
  than shrinking the population.
- **Sub-minute recordings may have no summary at all**, because none was
  generated. That is a classification signal, not an error to work around.
- **Proper nouns are mangled.** Names of people, products and companies arrive
  in several spellings, and numbers lose digits. Normalise, and treat
  transcript-only values as provisional.

## A local-files source

The simplest adapter needs no API at all: a directory of exported transcripts or
Markdown notes. Derive `id` from the filename, `title` from the first heading or
the filename, `start` from a date in the filename or the file's mtime, and
`duration_ms` from a duration line if the export includes one — or omit it and
accept that the rollup will report zero length.

Everything downstream — classification, thread-finding, the four output layers —
works identically. Only the enumeration changes.
