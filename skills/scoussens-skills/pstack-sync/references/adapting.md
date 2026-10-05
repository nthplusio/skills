# Profiling the harness and adapting pstack

pstack is written for Cursor. Adapting a skill rewrites each Cursor-specific construct into what the **running harness** supports, so the skill does here what it did in Cursor. Nothing about the harness is assumed: you discover it, record it in the harness profile, and adapt from the profile.

## The needs catalog

`pstack-sync/needs.json` lists every feature pstack relies on, harness-independent: what pstack uses it for, the Cursor constructs, the regex markers the script flags, the question to answer about any harness, and the usual fallback. It is the single source of truth for markers.

A Cursor construct you find that no need covers gets a new need in the catalog (with markers) before you adapt it, so the next sync flags it in every harness.

## The harness profile

`pstack-sync/harness/<harness>.md` answers the catalog for one harness. Start a new one from `harness/TEMPLATE.md`. It has two parts:

- **Destination**: where this harness loads shared skills from, how a change takes effect, how a running session reloads, and which other skill sources shadow it.
- **Needs**: one row per need ID, with a **support** level, the harness equivalent, and the source that proves it.

| Support | Meaning | Effect on sync |
| --- | --- | --- |
| `native` | The harness provides the Cursor construct as written. | Markers accepted automatically. |
| `keep` | Not provided, but harmless as written. | Markers accepted automatically. |
| `substitute` | A different construct does the same job. | Rewrite to the equivalent. |
| `partial` | Something covers part of the job. | Rewrite to it and state the gap in one sentence. |
| `none` | Nothing covers it. | Cut it and apply the catalog fallback. |

**Profile from evidence**, in this order: the tools and instructions in your own context (what you can call right now), the harness's skill and configuration docs, its CLI `--help`, and its config directories. Fill the Source column for every row. A support level you cannot source is a guess; mark it `none` until you can. Answer every need the catalog lists, including ones no current file flags; the script reports `profile_gaps` for flagged needs without a row.

## Adapting a file

Read every flagged file in full, scripts included; the markers are hints. For each construct, look up its need in the profile and apply the row. Keep each rewrite **minimal**: change the construct and the words that depend on it, and keep the skill's structure, voice, and intent, so upstream changes replay cleanly.

- A need at `none` that a skill's whole purpose depends on (for example `setup-pstack` with no model selection): leave the skill unadapted and propose adding its upstream name to `exclude` in `manifest.json`. Exclusion is the user's call.
- A `stale_transforms` entry means upstream rewrote a passage you adapted before. The old edit is in `transform.json` under the file's key; carry its intent onto the new passage.
- A row that turns out wrong: correct the profile, then re-adapt every file that used it.

A file is adapted when every flagged need is applied per its row, and a reread finds no instruction the harness cannot carry out.
