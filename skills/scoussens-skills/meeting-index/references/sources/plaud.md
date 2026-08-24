# Source adapter: Plaud

[Plaud](https://www.plaud.ai) is a hardware voice recorder with a companion app
that transcribes and auto-summarises each recording. Reached through its MCP
server, which exposes tools under `mcp__*_Plaud__*` — the middle segment depends
on how the server is registered, so discover the exact names rather than
assuming them.

Verified against a real account holding several hundred recordings.

## Tools

| Tool | Use |
| --- | --- |
| `list_files` | Enumerate recordings. The population step. |
| `get_note` | Per-recording AI summary. **The workhorse.** |
| `get_transcript` | Timestamped utterances, paginated. Quotes only. |
| `get_file` | Metadata *plus the full transcript*. Avoid — see below. |
| `get_current_user` | Cheap call; useful to clear expired auth. |

## Normalising a listing

`list_files` returns records shaped like this:

```json
{
  "id": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
  "name": "08-21 Weekly Meeting: Auth Migration, Endpoint Alignment",
  "created_at": "2026-08-21T19:25:37",
  "start_at": "2026-08-21T18:06:03.925000",
  "duration": 4769000
}
```

Map to the normalised record:

| Normalised | Plaud | Note |
| --- | --- | --- |
| `id` | `id` | 32 hex chars. Required by every other call. |
| `title` | `name` | Auto-generated. Names the *topic*, not the subject. |
| `start` | `start_at` | **UTC.** Falls back to `created_at` if absent. |
| `duration_ms` | `duration` | **Milliseconds**, not seconds. |

`scripts/rollup.py` accepts these Plaud field names directly, so a raw
`list_files` response can be saved and passed straight in with no conversion.

## Enumerating the window

`list_files` takes `date_from` / `date_to` (`YYYY-MM-DD`, inclusive) and
`query`, plus `page` / `page_size`.

**Use the dates.** `query` is a case-insensitive substring match on `name` only
— and because Plaud names recordings after their topic, it under-recalls badly.
Measured on one real week: `query` for the product's own name matched 9
recordings across 500 scanned, of which **2 fell inside a window that actually
held 41 meetings about it**. Run it as a cross-check if you like; never as the
population.

### The two truncation behaviours

- **With dates set**, the response carries `truncated: true` plus `scanned` and
  `matched`. You get a warning — narrow the range and chunk.
- **Without dates**, `page` / `page_size` caps at the page size and returns **no
  `truncated` field at all**. A clipped response is byte-identical to a complete
  one.

The second one has already caused a real failure: `page_size: 40` returned
exactly 40 records, stopping part-way through the earliest day, and the index
shipped five meetings and 2.8 hours short. Lead with dates, and re-list the
boundary days on their own to confirm nothing was clipped.

## Fetching summaries

`get_note` returns a structured summary — executive summary, per-topic
breakdown, decisions, action items with owners. That is most of what an index
needs, already extracted. Batch six to eight calls at a time.

Two Plaud-specific gotchas:

- **`get_note`'s own header date is sometimes wrong** — off by a day from when
  the meeting happened. The listing's `created_at` and the `MM-DD` prefix in
  `name` are authoritative; the summary header is not.
- **`token expired` errors are frequent** and can hit a whole batch at once.
  Retry — it usually clears on the next call, and `get_current_user` is a cheap
  way to force it. Transient 500s happen too.

### Do not reach for `get_file`

`get_file` bundles the full transcript with the metadata. One call on a
mid-length meeting returned **64,951 characters** and blew a context budget for
no benefit, since `list_files` already supplied name, timestamps and duration.
Use it only as a last-resort fallback when `get_note` will not return at all.

### Recordings with no summary

Very short recordings never get one generated, so `get_note` fails on them
permanently — a 16-second clip whose entire transcript was one word, for
instance. Treat a permanent failure on a sub-minute recording as confirmation it
was accidental, and exclude it rather than retrying.

## Timezone

`start_at` is UTC. The `get_note` summary header usually quotes local time, so
the offset is recoverable: subtract one recording's stated local time from its
`start_at` and pass the difference to `rollup.py --offset-hours`. Derive it;
never assume a zone.

## Transcription quality

Worth knowing before you quote anything. Across a single week of one account,
one product name appeared as four different spellings, a client's initials were
rendered as a shorter acronym in one meeting, a person's name appeared five
different ways with none correct, and a negative numeric constant lost a digit.
Normalise aggressively, prefer spellings the user has used, and mark anything
you have only from a transcript as provisional.
