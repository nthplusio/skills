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

**Profile the capability, not the construct.** A need names what pstack wants done (choose a model per role, ask the user, read past chats), not the Cursor feature that did it. Look for any way this harness achieves the same outcome, including a combination of features: a persisted per-role model config can be an always-loaded instructions file (to store it) plus a dispatch tool that takes a model or mode (to honor it). Each harness has its own variant; the profile row records that variant precisely enough that every skill applies it the same way. `none` means no combination works.

**Fill shared needs from discovery.** Discovery records these needs as harness facts any skill can read. Fill their rows from the entry discovery printed in step 1, and cite `discovery.json` and the field as the Source. When all of a need's fields are `null`, the need is `none`. When the entry lacks a fact a row needs, have `orchestration-discovery` inspect and save it, then fill the row.

| Need | Discovery field |
| --- | --- |
| `subagents` | `helpers.invoke`, `helpers.collect`, `helpers.blocks_caller` |
| `readonly-subagents` | `helpers.readonly` |
| `custom-subagents` | `helper_term`, `helpers.invoke` |
| `model-selection` | `models` |
| `ask-user` | `ask_user` |
| `background-agents` | `owners.launch`, `owners.resume` |
| `transcripts` | `owners.inspect` |
| `worktrees` | `owners.workspace_model`, `owners.launch` |
| `loop` | `monitoring.wake` |
| `skill-locations` | `skills.locations`, `skills.reload` |
| `persistent-rules` | `instructions` |

**Profile pstack's own needs from evidence.** The other needs (`role-model-config`, `modes`, `invocation-control`, `bugbot`, `cursor-product`, and `companion-skills`) are specific to pstack. Check the tools and instructions in your own context first (what you can call right now), then the harness's skill and configuration docs, its CLI `--help`, and its config directories.

Fill the Source column for every row. A support level you cannot source is a guess; mark it `none` until you can. Answer every need the catalog lists, including ones no current file flags; the script reports `profile_gaps` for flagged needs without a row.

## Adapting a file

Read every flagged file in full, scripts included; the markers are hints. For each construct, look up its need in the profile and apply the row. Keep each rewrite **minimal**: change the construct and the words that depend on it, and keep the skill's structure, voice, and intent, so upstream changes replay cleanly.

- A skill that configures a capability (for example `setup-pstack` writing the per-role model config) is rewritten to produce this harness's variant of that configuration, and every skill that reads the configuration is rewritten to read and honor the same variant. The profile row is the contract between them.
- Only a need at `none` that a skill's whole purpose depends on makes the skill an exclusion candidate: leave it unadapted and propose adding its upstream name to `exclude` in `manifest.json`. Exclusion is the user's call.
- A `stale_transforms` entry means upstream rewrote a passage you adapted before. Each entry holds the old edit's full `find` and `replace`, and on the sync that detects the change the file's `upstream_diff` shows what upstream rewrote. Carry the old `replace`'s intent onto the new passage; usually that is the old `replace` plus the upstream change.
- A row that turns out wrong: correct the profile, then re-adapt every file that used it.

A file is adapted when every flagged need is applied per its row, and a reread finds no instruction the harness cannot carry out.
