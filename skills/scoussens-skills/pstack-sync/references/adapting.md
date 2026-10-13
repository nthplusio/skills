# Profiling the harness and adapting pstack

pstack is written for Cursor. Adapting a skill rewrites each Cursor-specific construct into what the **running harness** supports, so the skill does here what it did in Cursor. Nothing about the harness is assumed: you discover it, record it in the harness profile, and adapt from the profile.

## The needs catalog

`pstack-sync/needs.json` lists every feature pstack relies on, harness-independent: what pstack uses it for, the Cursor constructs, the regex markers the script flags, the question to answer about any harness, the usual fallback, and, for a need harness discovery answers, the discovery fields. It is the single source of truth for markers and for which needs the profile owns.

A Cursor construct you find that no need covers gets a new need in the catalog (with markers) before you adapt it, so the next sync flags it in every harness.

## The harness profile

`.nthplusio-skills/pstack-sync/harness/<harness>.md` answers the catalog for one harness. That directory sits with `discovery.json`, so a plain copy of the skill pack does not replace it. The first run copies the shipped `pstack-sync/harness/<harness>.md` there when the pack has one. Start a harness the pack does not ship from `pstack-sync/harness/TEMPLATE.md`, and save the profile at the durable path. It has two parts:

- **Destination**: where this harness loads shared skills from, how a change takes effect, how a running session reloads, and which other skill sources shadow it.
- **Needs**: one row for each need without discovery fields, with a **support** level, the harness equivalent, and the source that proves it.

| Support | Meaning | Effect on sync |
| --- | --- | --- |
| `native` | The harness provides the Cursor construct as written. | Markers accepted automatically. |
| `keep` | Not provided, but harmless as written. | Markers accepted automatically. |
| `substitute` | A different construct does the same job. | Rewrite to the equivalent. |
| `partial` | Something covers part of the job. | Rewrite to it and state the gap in one sentence. |
| `none` | Nothing covers it. | Cut it and apply the catalog fallback. |

**Profile the capability, not the construct.** A need names what pstack wants done (choose a model per role, ask the user, read past chats), not the Cursor feature that did it. Look for any way this harness achieves the same outcome, including a combination of features: a persisted per-role model config can be an always-loaded instructions file (to store it) plus a dispatch tool that takes a model or mode (to honor it). Each harness has its own variant; the profile row records that variant precisely enough that every skill applies it the same way. `none` means no combination works.

## Needs that harness discovery answers

A need that names `discovery` fields in `needs.json` takes its facts from the repository's `.nthplusio-skills/discovery.json`, which `harness-discovery` owns, and has no row in the profile. `sync.py` reads the harness's entry and counts such a need as profiled once every field it names is recorded. The sync report's `harness_facts` gives those facts for each flagged need, and you adapt from them as you would from a row.

- A `null` field means the harness has no such operation. Rewrite with the catalog fallback, unless a combination of other features does the job.
- A field not yet recorded, or no entry for the harness, puts the need in `profile_gaps`. Run `harness-discovery` instead of writing the fact into the profile.
- A profile row for such a need overrides discovery. Add one only when pstack's Cursor construct works as written (`native`) or is harmless (`keep`), because only those levels change what `sync.py` does.

**Profile the rest from evidence**, in this order: the tools and instructions in your own context (what you can call right now), the harness's skill and configuration docs, its CLI `--help`, and its config directories. Fill the Source column for every row. A support level you cannot source is a guess; mark it `none` until you can. Answer every need the profile owns, including ones no current file flags; the script reports `profile_gaps` for flagged needs with neither a row nor discovered facts.

## Hand-offs and dependencies

pstack hands work to other skills. `sync.py` sorts each hand-off in a synced file into one of three cases.

- **Dependency.** A file hands off to a skill by writing `` `name` ``, `/name`, `**name**`, or a `../name/` link, and to a subagent definition (`<plugin>/agents/<name>.md` in `cursor/plugins`) by writing its name. The hand-off counts when exactly one plugin in scope provides the name. The scope is the referencing skill's own plugin, plus each plugin the skill names as `` `plugin` `` or "plugin plugin". The skill or definition then installs beside pstack and goes through the same rendering, markers, and transforms, and its own hand-offs are followed in turn. A name two in-scope plugins provide is reported under `dependencies.ambiguous` and not installed. A skill name an unmanaged skill already has is left to that skill and listed under `dependencies.existing`.
- **Companion.** A hand-off the skills directory will not have becomes a `companion-skills` marker on the file. That covers a Cursor built-in (the `` `create-skill` `` skill, the built-in babysit skill, `` `/add-plugin` ``), a skill from a plugin the file does not name, and a name in `exclude`. The profile's `companion-skills` row maps each companion to the harness's equivalent; a name the row does not mention in backticks is listed in `dependencies.unresolved`. A companion whose slash command another need's markers cover, such as `/loop`, belongs to that need instead. Once a file is adapted, the harness's own skills it names count as companions too; add them to the harness's `accept` regexes once so they stop flagging.
- **Excluded.** A name in `exclude` that a synced file still hands off to is listed under `dependencies.excluded`, with the files. Rewrite those hand-offs per the profile, or remove the name from `exclude`.

Subagent definitions install as `pstack-agents/<name>.md`, which is not a skill. Every file that names one is flagged under `custom-subagents`, and the profile row says how this harness dispatches it. In a harness without named subagents, that is a generic subagent whose prompt points at the definition file.

When a dependency installs for the first time, each file with a recorded adaptation that hands off to it gets a `dependencies` entry: an adaptation made while the dependency was missing may have cut the hand-off. Restore any hand-off it cut, then record the file.

## Adapting a file

Read every flagged file in full, scripts included; the markers are hints. For each construct, look up its need in the profile and apply the row, or apply the discovered facts the report gives in `harness_facts`. Keep each rewrite **minimal**: change the construct and the words that depend on it, and keep the skill's structure, voice, and intent, so upstream changes replay cleanly.

- A skill that configures a capability (for example `setup-pstack` writing the per-role model config) is rewritten to produce this harness's variant of that configuration, and every skill that reads the configuration is rewritten to read and honor the same variant. The profile row is the contract between them.
- Only a need at `none` that a skill's whole purpose depends on makes the skill an exclusion candidate: leave it unadapted and propose adding its upstream name to `exclude` in `manifest.json`. Exclusion is the user's call.
- A `stale_transforms` entry means upstream rewrote a passage you adapted before. Each entry holds the old edit's full `find` and `replace`, and on the sync that detects the change the file's `upstream_diff` shows what upstream rewrote. Carry the old `replace`'s intent onto the new passage; usually that is the old `replace` plus the upstream change.
- A row that turns out wrong: correct the profile, then re-adapt every file that used it.

A file is adapted when every flagged need is applied per its row, and a reread finds no instruction the harness cannot carry out.
