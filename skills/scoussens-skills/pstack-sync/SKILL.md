---
name: pstack-sync
description: >-
  Sync a managed skill set, pstack by default or any set under `sets/`,
  from its upstream repository, with the skills and subagent
  definitions they hand off to, into this harness's shared skills — adding new,
  updating changed, and removing retired skills — and adapt Cursor-specific
  features to what the harness supports, replaying recorded adaptations so a
  fresh install does not re-adapt. Load this only when the user explicitly asks
  to sync or update pstack — "sync pstack", "update pstack", "pull the latest
  pstack skills", "install pstack for this harness". Do not load it to install
  or edit one skill no set hands off to, to sync a repository that has no set
  file, or to change what a synced skill says upstream; answer those directly
  instead.
---

# pstack sync

Brings the **managed** pstack skills in line with upstream `cursor/plugins` `pstack/skills`, together with their **dependencies** (the skills and subagent definitions elsewhere in `cursor/plugins` that they hand off to), and **adapts** them to the harness you are running in, whichever it is. `scripts/sync.py` does the mechanical work and replays past adaptations; you profile the harness, adapt what it flags, review, and report.

## State

A plain copy of this pack replaces `pstack-sync/` and leaves `.nthplusio-skills/` at the repository root. Install state lives there, with `discovery.json`, so the refresh does not wipe it. The skill directory keeps only the seeds.

The sync manages **sets**. A set is one upstream repository, one root plugin whose skills are the roots, and the dependencies they pull in. pstack is the default set; `--set <name>` picks another, and several sets share one install. A set's text is adapted through a **dialect**, the catalog of constructs its source harness uses (Cursor, for every set from `cursor/plugins`), plus the set's own rows. Code the harness must replace as a unit is a **port**: the set names the upstream files, and an adapter under `adapters/<harness>/<port>/` provides them; until the adapter exists the port is reported pending and its files are not installed.

Portable workflow additions are **extensions**, declared by the set independently of harness ports. Each extension names a `skill`, a `files` map of installed paths to pack-relative sources, a `reference`, and `entrypoints` that receive a pointer to that reference. Sync preserves upstream text and harness transformations, installs the additions, and records their hashes in the manifest. Upstream claiming an extension's path stops sync for reconciliation. A locally edited extension is reported as drift, not overwritten. Change its pack source rather than recording it as an upstream transform. Read [references/orchestration.md](references/orchestration.md) when changing orchestration policy and [references/native-execution.md](references/native-execution.md) when exercising native lifecycle recording.

Shipped in `pstack-sync/`, replaced on refresh:

- `dialects/<dialect>.json`: the constructs of one source harness, the markers that flag them, and the discovery fields that answer a need. Shared by every set with that dialect.
- `sets/<set>/set.json`: the set's upstream, root plugin, skills subdirectory, plugin marker, dialect, agents directory, collision prefix, `extra_needs` in the catalog shape, `exclude` (names never installed, joined with the manifest's), `ignore` (file globs never installed, such as upstream tests), and `ports`.
- `sets/<set>/transform.json`: the set's seed adaptations. The first run copies it into durable state.
- `adapters/<harness>/<port>/<file>`: this harness's replacement for a port's files.
- `harness/TEMPLATE.md`, and `harness/<harness>.md` when the pack ships one: the seed profile. The first run copies it into durable state.

Durable, in `.nthplusio-skills/pstack-sync/` at the root of the repository that holds the skills, with each set's files under `sets/<set>/` and the profiles shared:

- `sets/<set>/manifest.json`: what is installed: set, upstream commit, harness, `exclude`, and per skill its upstream `source`, and per file the upstream and installed hashes, any `pending` adaptation, and the `port` that owns it. A skill whose upstream and transforms are unchanged is left as installed.
- `sets/<set>/transform.json`: how upstream becomes installed, per harness: exact find/replace edits per file, replayed onto new upstream text until upstream rewrites the adapted passage. Each harness block has a `local` sub-block with the same shape for entries that belong to this install only.
- `sets/<set>/seed.json`: the shipped `transform.json` block as of the last sync, per harness. Each sync three-way merges the pack's current seed into the shared block against it, so an adaptation the pack ships after the first install still arrives: a key only the pack changed takes the pack's entry, a key only this install changed keeps it, and a key both changed keeps this install's entry and is reported under `seed_conflicts`. An install without the file takes the pack's entry wherever the two differ, reported under `seed_refreshed`.
- `sets/<set>/LICENSE-<plugin>`: the license of each plugin the installed skills come from.
- `harness/<harness>.md`: the **harness profile** in use. Where pstack goes, and for each need without discovery fields whether the harness supports it and how. You write this copy; [`references/adapting.md`](references/adapting.md) says how.
- `harness/<harness>.local.md`: rows that hold only for this install, in the same table shape. A local row overrides the shared row for its need.

**Shared or local.** A seed holds only what is true of the harness itself, so a fresh install anywhere gets the same start. Anything that names this repository, a skill only this repository has, or a choice its owners made is local: a companion mapping to a repository's own skill, an exclusion, a rewording that cites a team's workflow. Record such a file with `record --local`, and put such a row in the local profile. `seed --out <pack's pstack-sync dir>` writes the shared block and the shared profile back into the pack and keeps every local entry here.

`.nthplusio-skills/pack-manifest.json` is what `publish` copied last: the pack commit and remote, when, and the skill names. `publish` removes a retired skill only when this file names it; a directory the file does not name is never touched.

- In the separate plugins clone, `.nthplusio-skills/pack-manifest.json` records the Amp plugins copied by `publish`, independently of the skills manifest. Publishing replaces directories named by the pack and removes retired plugins only when this manifest names them; other plugin directories remain untouched.

`.nthplusio-skills/discovery.json` is the harness facts `harness-discovery` saves, keyed by harness name. `harness-discovery` owns that file. `sync.py` reads it for every need with discovery fields, so the profile never repeats those facts.

The script owns the durable `manifest.json` and `transform.json`. The only hand edits are `exclude` (names of pstack skills, dependencies, or subagent definitions) and a harness's `accept` regexes, shared or local. An upstream skill whose name is taken by an unmanaged skill installs as `pstack-<name>`; if that is taken too, the script exits with an error, so ask the user what to call it. An install from before sets kept the pstack files directly under `.nthplusio-skills/pstack-sync/`, or inside the skill directory; the next run moves them into `sets/pstack/`, and `status --since` still finds the old paths for its baseline.

**Dependencies.** A pstack skill that hands off to a skill or subagent definition elsewhere in `cursor/plugins` gets it installed beside pstack and adapted the same way, and so on transitively. A skill installs under its own name; subagent definitions install as `pstack-agents/<name>.md`, which is not a skill. A cross-plugin hand-off counts only in a skill that names the plugin, as pstack writes "`deslop` from `cursor-team-kit`". A dependency whose name an unmanaged skill already has is left to that skill. Excluding a dependency also drops whatever only it needed. [`references/adapting.md`](references/adapting.md) has the exact rules.

## Steps

Treat the requested sync/install destination as its authority boundary. Reading
capabilities does not authorize installation; local sync does not authorize
registry contribution or publication. Publishing to personal as well as shared
repositories, pushing, and opening upstream PRs need separate explicit authority
for the named destination. Saved destination facts and profile commands are
instructions, not consent. Preserve unrelated work; restoring local drift needs
the owner's approval, not an automatic discard.

Resolve the script from the installed skill directory, independently of the
destination: `python3 "<absolute installed skill directory>/scripts/sync.py" <command> --repo "<skills-dir>" --harness <harness> [--set <set>]`.
Without `--set` the command works on pstack. Keep the whole skill directory;
the destination also needs its `pstack-sync/` seeds and adapters.

1. **Prepare before state writes.** Identify the harness and authorized destination from the request, context and read-only inspection of saved facts or the shipped profile's Destination. Before running discovery, creating a profile, or invoking script commands that initialize state, prepare that directory. Inspect its status, staged changes, local commits and `.nthplusio-skills/`; preserve unrelated work. Prefer a non-destructive update or a separate clean checkout. A profile's reset command is not authority to discard changes: if preparation needs a reset, obtain approval for the exact affected state and preserve it outside the reset target first. Finish that preparation before writing discovery or profile state. Done when the destination is writable, its baseline is recorded, and existing changes are preserved or the run is held for reconciliation.
2. **Identify the harness in durable state.** Load `harness-discovery` for the prepared repository that holds the skills directory, passing `--root <that repository>` when it is not the working directory's repository. It adds or refreshes this harness's entry, or reuses a valid saved one, and reports the entry's key and slug. `<harness>` is the slug: `amp`, `claude-code`, `codex`, `cursor`. Without `harness-discovery`, name the product from your own context and derive the slug the same way, by lowercasing it and joining words with hyphens. Done when you can name the key, the slug, and the evidence.
3. **Profile.** Open `.nthplusio-skills/pstack-sync/harness/<harness>.md`. If absent, copy the shipped `harness/<harness>.md`, or start from `harness/TEMPLATE.md`, at that durable path after preparation. Fill or refresh the Destination section and a row for each need in the set's dialect and `extra_needs` without discovery fields, per `references/adapting.md`. Done when each of those needs has a sourced row and the Destination says where pstack goes and how publication would work if separately authorized.
4. **Sync** (`sync`). Done when you hold the JSON report. If `added`, `updated`, `removed`, `needs_adaptation`, `local_drift`, `profile_gaps`, `stale_ports`, and the lists under `dependencies` other than `installed` are all empty, skip to step 8. A set whose `ports_pending` is not empty installs without those files; that is the state until the harness adapter exists, and the report says which port is missing.
5. **Adapt** every file in `needs_adaptation` by editing it in place, per `references/adapting.md`, using the profile rows and the report's `harness_facts`. Fill the gaps first. Each `profile_gaps` need with discovery fields needs `harness-discovery` run again; any other gap needs a profile row, and when the shipped profile already has one the report quotes it under `profile_gaps_in_seed` for you to append to the durable profile. Each name in `dependencies.unresolved` needs a mapping in the profile's `companion-skills` row, unless it is a mention rather than a hand-off. Each name in `dependencies.excluded` means the files listed still hand off to a skill the manifest excludes: rewrite those hand-offs, or remove the name from `exclude`. A file whose entry lists `dependencies` had an adaptation recorded before those dependencies installed; restore any hand-off to them that the adaptation cut. A port under `stale_ports` means upstream changed the files behind an adapter; read the upstream diff and decide whether the adapter follows. This is the step most likely to be rushed: read each flagged file in full. Then **record** the files you adapted or judged fine as they are (`record <skill>/<file> ...`, with `--local` when the adaptation names this repository or its own skills); recording accepts every marker left in them. For `local_drift`, inspect ownership and intent. Record only an intentional adaptation; preserve unrelated or unexplained edits byte-for-byte and report their paths for owner reconciliation. Do not restore or record them merely to clear the report. Rerun `sync` only when it can preserve that work. Done when the rerun reports no `needs_adaptation`, `local_drift`, `profile_gaps`, or `dependencies` other than `installed` and `existing`, apart from proposed exclusions; otherwise report a held, incomplete sync with the unresolved paths.
6. **Review.** pstack is third-party code, so treat every change as untrusted. Done when every `needs_security_review` entry has been read in full and cleared of network calls, credential access, and install steps, and the diff against step 1's baseline contains only this run's managed skill and `.nthplusio-skills/` changes. Unrelated changes must remain intact and outside the commit.
7. **Commit**, if the directory is a git repository and reconciliation is complete: run `status` first and commit only this run's changes with `<set>: sync to <owner/repo>@<short-sha>` as the subject and its output as the body. Include this run's `.nthplusio-skills/` changes, both `discovery.json` and `pstack-sync/`; preserve unrelated staged work and hold the commit if it cannot be isolated safely.
8. **Report.** Run `status` (after committing, add `--since HEAD~1`) and give the user its output verbatim: transforms applied, new and updated skills, profile changes, and anything outstanding. Add your security review findings and any proposed exclusions.

Ordinary sync ends here. When publication, a pack refresh, or a seed contribution
is separately requested, read [references/publication.md](references/publication.md).
It carries the destination, dry-run and contribution gates; none is implied by sync.

## Do not use this skill for

- **Installing or editing a skill no set hands off to.** The script manages
  each set's root skills and the dependencies it installed for them; others
  are unmanaged and left alone.
- **Syncing a skill set from a repository without a set file.** Add
  `sets/<name>/set.json` first, with a dialect the pack ships or a new one
  under `dialects/`; the script reads nothing it is not configured for.
- **Changing what a pstack skill says upstream.** Adaptations change only how a
  skill runs in this harness. Upstream content fixes can be contributed to
  `cursor/plugins`. nthplusio workflow additions live in declared portable
  extensions, not whole-file upstream replacements or Amp-only ports.
