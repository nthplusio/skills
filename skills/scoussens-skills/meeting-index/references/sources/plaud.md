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
  "name": "01-15 Weekly Sync: Example Topic A, Example Topic B",
  "created_at": "2026-01-15T16:00:00",
  "start_at": "2026-01-15T15:00:00.000000",
  "duration": 3600000
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
A `query` for a product's own name can match a handful of recordings across the
whole library, and only one or two of them inside **a window that holds dozens
of meetings about it**. Run it as a cross-check if you like; never as the
population.

### The two truncation behaviours

- **With dates set**, the response carries `truncated: true` plus `scanned` and
  `matched`. You get a warning — narrow the range and chunk.
- **Without dates**, `page` / `page_size` caps at the page size and returns **no
  `truncated` field at all**. A clipped response is byte-identical to a complete
  one.

The second one fails silently: `page_size: 40` can return exactly 40 records
that stop part-way through the earliest day, and an index built from them ships
meetings short with no warning. Lead with dates, and re-list the boundary days
on their own to confirm nothing was clipped.

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
mid-length meeting can return **tens of thousands of characters** and blow a
context budget for no benefit, since `list_files` already supplied name, timestamps and duration.
Use it only as a last-resort fallback when `get_note` will not return at all.

### Recordings with no summary

Very short recordings never get one generated, so `get_note` fails on them
permanently — a clip of a few seconds whose entire transcript is one word, for
instance. Treat a permanent failure on a sub-minute recording as confirmation it
was accidental, and exclude it rather than retrying.

## Timezone

`start_at` is UTC even when its string omits the offset. The `get_note` summary
header can suggest a local offset, but its date can be wrong; confirm the local
datetime before deriving an offset. Subtract the UTC datetime from the local
datetime for the same instant: 10:00 local minus 15:00 UTC gives `-5`.
Follow [the rollup instructions](../../SKILL.md#roll-up-the-numbers-with-the-script)
for installed script paths and fixed-offset limits, including windows that cross
a daylight-saving transition. One recording's offset does not establish the
offset for the entire window.

## Transcription quality

Worth knowing before you quote anything. Within a single week, one product name
can appear in several spellings, an organisation's initials can come back as a
different acronym, a person's name can appear several ways with none correct,
and a numeric constant can lose a digit.
Normalise aggressively, prefer spellings the user has used, and mark anything
you have only from a transcript as provisional.
